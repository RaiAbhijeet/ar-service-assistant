"""Dense (semantic) retrieval: embeds the query, ranks chunks by cosine similarity.

Per CLAUDE.md section 2, this only ever talks to the locally-running Ollama
instance for embedding — no cloud API.
"""

import asyncpg
import httpx

from app.retrieval.models import RetrievedChunk, chunk_from_row

_EMBED_TIMEOUT_S = 30.0


class EmbedQueryError(RuntimeError):
    """Raised when Ollama's /api/embed response doesn't contain a usable vector."""


async def embed_query(
    query: str,
    *,
    ollama_host: str,
    model: str,
    client: httpx.AsyncClient | None = None,
) -> list[float]:
    """Embed a single query string, returning its vector.

    A separate, simpler function from `ingest.embed.embed_chunks`: a query
    is always exactly one string, so there's no batching loop to share.
    """
    owns_client = client is None
    http_client = client if client is not None else httpx.AsyncClient(timeout=_EMBED_TIMEOUT_S)
    try:
        response = await http_client.post(
            f"{ollama_host}/api/embed",
            json={"model": model, "input": [query]},
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != 1:
            got = len(embeddings) if isinstance(embeddings, list) else "no"
            raise EmbedQueryError(
                f"Ollama returned {got} embeddings for a single query "
                f"(model={model!r}); expected exactly one vector."
            )
        vector: list[float] = embeddings[0]
        return vector
    finally:
        if owns_client:
            await http_client.aclose()


async def search_dense(
    conn: asyncpg.Connection,
    *,
    object_id: str,
    query_vector: list[float],
    top_k: int,
) -> list[RetrievedChunk]:
    """Return the `top_k` chunks closest to `query_vector` by cosine similarity.

    The vector is passed as a pgvector text literal and cast in SQL
    (`$2::text::vector`) rather than relying on
    `pgvector.asyncpg.register_vector` having been called on this
    connection — callers may be using a plain connection-pool connection
    with no per-connection codec set up. The extra `::text` matters, not
    just style: a bare `$2::vector` makes Postgres infer $2's type as
    `vector`, so *if* register_vector has been applied on this connection
    (e.g. because the caller's pool also writes embeddings elsewhere),
    asyncpg routes the plain string through pgvector's registered codec —
    which requires a real `Vector`/list/ndarray and raises `DataError` on a
    string. Casting through `::text` first keeps $2 inferred as plain text,
    so it always goes through ordinary string encoding no matter what the
    connection has registered; confirmed against a real connection with
    register_vector applied.
    """
    rows = await conn.fetch(
        """
        SELECT id, object_id, manual_id, page, section, step_no, text, figure_ids,
               1 - (embedding <=> $2::text::vector) AS dense_score
        FROM chunks
        WHERE object_id = $1 AND embedding IS NOT NULL
        ORDER BY embedding <=> $2::text::vector
        LIMIT $3
        """,
        object_id,
        vector_literal(query_vector),
        top_k,
    )
    return [chunk_from_row(row, dense_score=row["dense_score"]) for row in rows]


def vector_literal(vector: list[float]) -> str:
    """Render a vector in pgvector's text input format: "[0.1,0.2,...]"."""
    return "[" + ",".join(str(v) for v in vector) + "]"
