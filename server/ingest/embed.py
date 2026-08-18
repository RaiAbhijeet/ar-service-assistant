"""Embeds chunks with bge-m3 via Ollama and writes them into Postgres.

Batches requests to Ollama's `/api/embed` endpoint (not the older
single-prompt `/api/embeddings`) so a manual's few hundred chunks don't mean
a few hundred round trips. Per CLAUDE.md section 2, this only ever talks to
the locally-running Ollama instance — nothing here reaches the internet.
"""

from collections.abc import Sequence

import asyncpg
import httpx

from app.telemetry.logging import get_logger
from ingest.chunk import Chunk

logger = get_logger()

_BATCH_SIZE = 16
_EMBED_TIMEOUT_S = 120.0


class EmbedError(RuntimeError):
    """Raised when Ollama's /api/embed response doesn't match the request."""


async def embed_chunks(
    chunks: Sequence[Chunk],
    *,
    ollama_host: str,
    model: str,
    client: httpx.AsyncClient | None = None,
) -> list[list[float]]:
    """Return one embedding vector per chunk, in the same order as `chunks`."""
    if not chunks:
        return []

    owns_client = client is None
    http_client = client if client is not None else httpx.AsyncClient(timeout=_EMBED_TIMEOUT_S)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[start : start + _BATCH_SIZE]
            response = await http_client.post(
                f"{ollama_host}/api/embed",
                json={"model": model, "input": [c.text for c in batch]},
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                got = len(embeddings) if isinstance(embeddings, list) else "no"
                raise EmbedError(
                    f"Ollama returned {got} embeddings for a batch of {len(batch)} chunks "
                    f"(model={model!r}). Refusing to store misaligned vectors."
                )
            vectors.extend(embeddings)
            logger.info("ingest.embed.batch", batch_size=len(batch), total_done=len(vectors))
    finally:
        if owns_client:
            await http_client.aclose()

    return vectors


async def store_chunks(
    chunks: Sequence[Chunk],
    vectors: Sequence[list[float]],
    *,
    object_id: str,
    conn: asyncpg.Connection,
) -> None:
    """Replace `object_id`'s rows in `chunks` with `chunks` + `vectors`.

    Deletes the object's existing rows first — chunk.py's boundary
    heuristics can shift between runs, so there's no stable per-chunk
    identity to upsert against (see schema.sql). The connection must already
    have `pgvector.asyncpg.register_vector` applied so a plain `list[float]`
    can be passed as the `embedding` column value.
    """
    if len(chunks) != len(vectors):
        raise EmbedError(
            f"{len(chunks)} chunks but {len(vectors)} vectors — refusing to store misaligned data."
        )

    async with conn.transaction():
        await conn.execute("DELETE FROM chunks WHERE object_id = $1", object_id)
        await conn.executemany(
            """
            INSERT INTO chunks
                (object_id, manual_id, page, section, step_no, text, figure_ids, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            [
                (
                    c.object_id,
                    c.manual_id,
                    c.page,
                    c.section,
                    c.step_no,
                    c.text,
                    c.figure_ids,
                    vec,
                )
                for c, vec in zip(chunks, vectors, strict=True)
            ],
        )
    logger.info("ingest.embed.stored", object_id=object_id, count=len(chunks))
