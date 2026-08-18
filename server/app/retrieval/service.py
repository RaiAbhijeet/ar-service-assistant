"""Orchestrates hybrid retrieval: embed -> dense + lexical -> fuse -> threshold.

Returning an empty list is a valid, expected outcome (CLAUDE.md section 2,
ADR-0006) — refusing to answer rather than fabricating one from a weak match.
"""

import asyncpg
import httpx

from app.retrieval.dense import embed_query, search_dense
from app.retrieval.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion
from app.retrieval.lexical import search_lexical
from app.retrieval.models import RetrievedChunk
from app.telemetry.logging import get_logger

logger = get_logger()


class RetrievalService:
    """Hybrid dense+lexical retrieval over one object's ingested manuals."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        ollama_host: str,
        embed_model: str,
        min_retrieval_score: float,
        rrf_k: int = DEFAULT_RRF_K,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._pool = pool
        self._ollama_host = ollama_host
        self._embed_model = embed_model
        self._min_retrieval_score = min_retrieval_score
        self._rrf_k = rrf_k
        self._http_client = http_client

    async def search(self, query: str, *, object_id: str, top_k: int) -> list[RetrievedChunk]:
        """Return up to `top_k` chunks for `query`, or `[]` if nothing is close enough.

        The refuse/answer decision is made on the closest single dense
        match's raw cosine similarity, not the RRF fused score — see
        fusion.py's docstring for why. RRF only decides display order among
        results once that bar is already cleared. Lexical search is skipped
        entirely when refusing, since its result wouldn't be used anyway.
        """
        query_vector = await embed_query(
            query,
            ollama_host=self._ollama_host,
            model=self._embed_model,
            client=self._http_client,
        )

        async with self._pool.acquire() as conn:
            dense_results = await search_dense(
                conn, object_id=object_id, query_vector=query_vector, top_k=top_k
            )

            top_dense_score = dense_results[0].dense_score if dense_results else None
            if not dense_results or (top_dense_score or 0.0) < self._min_retrieval_score:
                logger.info(
                    "retrieval.refused",
                    object_id=object_id,
                    top_dense_score=top_dense_score,
                    threshold=self._min_retrieval_score,
                )
                return []

            lexical_results = await search_lexical(
                conn, object_id=object_id, query=query, top_k=top_k
            )

        fused = reciprocal_rank_fusion(dense_results, lexical_results, k=self._rrf_k)
        return fused[:top_k]
