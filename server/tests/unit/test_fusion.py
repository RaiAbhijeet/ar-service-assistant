"""Unit tests for app.retrieval.fusion. Pure Python — no real infra needed."""

from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import RetrievedChunk


def _chunk(id_: int, **scores: float) -> RetrievedChunk:
    return RetrievedChunk(
        id=id_,
        object_id="obj",
        manual_id="man",
        page=1,
        section="Sec",
        step_no=None,
        text=f"chunk {id_}",
        figure_ids=[],
        **scores,
    )


def test_doc_in_both_lists_ranks_first_and_keeps_both_scores() -> None:
    dense = [_chunk(1, dense_score=0.9), _chunk(2, dense_score=0.5)]
    lexical = [_chunk(1, lexical_score=0.8)]

    fused = reciprocal_rank_fusion(dense, lexical)

    assert [c.id for c in fused] == [1, 2]
    assert fused[0].dense_score == 0.9
    assert fused[0].lexical_score == 0.8


def test_dense_only_doc_is_included_with_no_lexical_score() -> None:
    dense = [_chunk(1, dense_score=0.9)]

    fused = reciprocal_rank_fusion(dense, [])

    assert [c.id for c in fused] == [1]
    assert fused[0].lexical_score is None


def test_lexical_only_doc_is_included_with_no_dense_score() -> None:
    lexical = [_chunk(1, lexical_score=0.7)]

    fused = reciprocal_rank_fusion([], lexical)

    assert [c.id for c in fused] == [1]
    assert fused[0].dense_score is None


def test_higher_rank_in_either_list_fuses_higher() -> None:
    dense = [_chunk(1, dense_score=0.9), _chunk(2, dense_score=0.85)]

    fused = reciprocal_rank_fusion(dense, [])

    assert [c.id for c in fused] == [1, 2]
    assert fused[0].fused_score is not None
    assert fused[1].fused_score is not None
    assert fused[0].fused_score > fused[1].fused_score


def test_smaller_k_widens_the_score_spread_between_ranks() -> None:
    dense = [_chunk(1, dense_score=0.9), _chunk(2, dense_score=0.8)]

    fused_default = reciprocal_rank_fusion(dense, [])
    fused_small_k = reciprocal_rank_fusion(dense, [], k=1)

    assert fused_small_k[0].fused_score is not None
    assert fused_small_k[1].fused_score is not None
    assert fused_default[0].fused_score is not None
    assert fused_default[1].fused_score is not None

    spread_small_k = fused_small_k[0].fused_score - fused_small_k[1].fused_score
    spread_default = fused_default[0].fused_score - fused_default[1].fused_score
    assert spread_small_k > spread_default


def test_empty_inputs_return_empty_list() -> None:
    assert reciprocal_rank_fusion([], []) == []
