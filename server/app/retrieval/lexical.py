"""Lexical (keyword) retrieval: Postgres full-text search, German configuration.

Uses `websearch_to_tsquery` (natural search-engine-style syntax — quoted
phrases, `-exclude`) against the `text_search` generated column and GIN
index `ingest/schema.sql` creates, ranked with `ts_rank`.
"""

import asyncpg

from app.retrieval.models import RetrievedChunk, chunk_from_row


async def search_lexical(
    conn: asyncpg.Connection,
    *,
    object_id: str,
    query: str,
    top_k: int,
) -> list[RetrievedChunk]:
    """Return the `top_k` chunks best matching `query` by German full-text rank."""
    rows = await conn.fetch(
        """
        SELECT id, object_id, manual_id, page, section, step_no, text, figure_ids,
               ts_rank(text_search, websearch_to_tsquery('german', $2)) AS lexical_score
        FROM chunks
        WHERE object_id = $1 AND text_search @@ websearch_to_tsquery('german', $2)
        ORDER BY lexical_score DESC
        LIMIT $3
        """,
        object_id,
        query,
        top_k,
    )
    return [chunk_from_row(row, lexical_score=row["lexical_score"]) for row in rows]
