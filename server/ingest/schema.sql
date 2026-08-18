-- Ingestion output schema.
--
-- Applied idempotently by ingest.run before every ingest run (CREATE ... IF
-- NOT EXISTS throughout). This is a single source of truth for one table,
-- not a migration framework — introducing one (e.g. alembic) is deferred
-- until there's a second schema change to migrate between (CLAUDE.md
-- section 6: no speculative abstraction).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    object_id   TEXT NOT NULL,
    manual_id   TEXT NOT NULL,
    page        INTEGER NOT NULL,
    section     TEXT NOT NULL,
    step_no     INTEGER,             -- NULL for non-numbered chunks (intro text, single-action bullets)
    text        TEXT NOT NULL,
    figure_ids  TEXT[] NOT NULL DEFAULT '{}',
    embedding   VECTOR(1024)         -- bge-m3. NULL until ingest.embed runs.
);

-- ingest.run replaces an object's rows wholesale on re-ingest rather than
-- upserting individual chunks — chunk.py's boundary heuristics can shift
-- between runs, so there's no stable per-chunk identity to upsert against.
CREATE INDEX IF NOT EXISTS chunks_object_id_idx ON chunks (object_id);

-- Dense retrieval side of the hybrid search (see ADR-0003).
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Lexical retrieval side. This is Postgres' built-in "german" text-search
-- configuration (snowball stemming), not the literal BM25 scoring formula —
-- it's the lexical half of the hybrid BM25-style + dense RRF retrieval
-- described in ADR-0003, using ts_rank at query time.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_search tsvector
    GENERATED ALWAYS AS (to_tsvector('german', text)) STORED;

CREATE INDEX IF NOT EXISTS chunks_text_search_gin_idx
    ON chunks USING GIN (text_search);
