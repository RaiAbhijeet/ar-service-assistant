"""Reciprocal Rank Fusion (RRF): merges two ranked lists into one.

RRF scores a document by summing `1 / (k + rank)` across every ranked list
it appears in (rank is 1-based; a list it's absent from contributes 0).
`k=60` is the constant from the original RRF paper (Cormack, Clarke &
Buettcher, 2009) — large enough that no single list's #1 result dominates
the fused order by itself.

RRF decides *display order* only. Whether to answer at all is a separate
decision made in `service.py`, using the top result's raw dense cosine
similarity — an RRF score is a rank-based construct, not a similarity
measure, and isn't meaningfully comparable to a fixed 0-1 threshold.
"""

from app.retrieval.models import RetrievedChunk

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    dense_results: list[RetrievedChunk],
    lexical_results: list[RetrievedChunk],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """Merge two ranked chunk lists into one, ordered by fused RRF score.

    A chunk appearing in both lists keeps both its `dense_score` and
    `lexical_score`; its position in each list determines `fused_score`.
    Does not mutate `dense_results`/`lexical_results` or the chunk objects
    in them — each chunk is copied on first use, so callers can safely
    reuse the same result lists afterward (e.g. to fuse again with a
    different `k`).
    """
    by_id: dict[int, RetrievedChunk] = {}
    fused_scores: dict[int, float] = {}

    for results in (dense_results, lexical_results):
        for rank, chunk in enumerate(results, start=1):
            existing = by_id.get(chunk.id)
            if existing is None:
                by_id[chunk.id] = chunk.model_copy()
                fused_scores[chunk.id] = 0.0
            else:
                # Fill in whichever score field this list carries that the
                # other list left unset — a chunk found by both keeps both.
                if chunk.dense_score is not None and existing.dense_score is None:
                    existing.dense_score = chunk.dense_score
                if chunk.lexical_score is not None and existing.lexical_score is None:
                    existing.lexical_score = chunk.lexical_score
            fused_scores[chunk.id] += 1.0 / (k + rank)

    fused_chunks = list(by_id.values())
    for chunk in fused_chunks:
        chunk.fused_score = fused_scores[chunk.id]

    fused_chunks.sort(key=lambda c: c.fused_score or 0.0, reverse=True)
    return fused_chunks
