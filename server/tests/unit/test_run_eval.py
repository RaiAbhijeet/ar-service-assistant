"""Unit tests for eval.run_eval's scoring logic. Pure Python — no DB/Ollama.

Per CLAUDE.md section 7 ("no network in unit tests"), these exercise
`score_entry` / `aggregate_metrics` directly against fake `RetrievedChunk`
lists rather than going through `run_eval()`, which needs a real Postgres
pool and is exercised by `make eval` instead.
"""

import pytest

from app.retrieval.models import RetrievedChunk
from eval.run_eval import EntryResult, aggregate_metrics, score_entry
from eval.schema import GoldenEntry


def _chunk(page: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        id=page,
        object_id="obj",
        manual_id="man",
        page=page,
        section="Sec",
        step_no=None,
        text=text,
        figure_ids=[],
    )


def _answerable(
    *, expected_pages: list[int], expected_keywords: list[str] | None = None
) -> GoldenEntry:
    return GoldenEntry(
        id="g001",
        question="Frage?",
        expected_pages=expected_pages,
        expected_keywords=expected_keywords or ["Klarspueler"],
        must_refuse=False,
    )


def _refusal() -> GoldenEntry:
    return GoldenEntry(
        id="g002",
        question="Nicht im Handbuch?",
        expected_pages=[],
        expected_keywords=[],
        must_refuse=True,
    )


# --------------------------------------------------------------------- score_entry


def test_answerable_entry_full_recall_and_keyword_hit() -> None:
    entry = _answerable(expected_pages=[25, 26], expected_keywords=["Klarspueler", "r05"])
    retrieved = [_chunk(25, "... Klarspueler r05 ..."), _chunk(26, "...")]

    result = score_entry(entry, retrieved)

    assert result.recall_at_5 == 1.0
    assert result.keyword_hit == 1.0
    assert result.refusal_correct is None


def test_answerable_entry_partial_recall_only_counts_pages_in_top_5() -> None:
    entry = _answerable(expected_pages=[25, 26, 99])
    retrieved = [_chunk(25, "Klarspueler"), _chunk(30, "irrelevant")]

    result = score_entry(entry, retrieved)

    assert result.recall_at_5 == pytest.approx(1 / 3)


def test_answerable_entry_keyword_hit_is_case_insensitive_substring() -> None:
    entry = _answerable(expected_pages=[1], expected_keywords=["KLARSPUELER", "Fehlt"])
    retrieved = [_chunk(1, "hier steht klarspueler irgendwo")]

    result = score_entry(entry, retrieved)

    assert result.keyword_hit == pytest.approx(0.5)


def test_answerable_entry_that_gets_refused_scores_zero_not_none() -> None:
    entry = _answerable(expected_pages=[25])
    result = score_entry(entry, [])

    assert result.recall_at_5 == 0.0
    assert result.keyword_hit == 0.0
    assert result.refusal_correct is None


def test_refusal_entry_correctly_refused() -> None:
    result = score_entry(_refusal(), [])

    assert result.refusal_correct is True
    assert result.recall_at_5 is None
    assert result.keyword_hit is None


def test_refusal_entry_incorrectly_answered() -> None:
    result = score_entry(_refusal(), [_chunk(1, "sollte nicht zurueckkommen")])

    assert result.refusal_correct is False


def test_recall_at_5_ignores_pages_beyond_the_top_5() -> None:
    entry = _answerable(expected_pages=[6])
    # 6 retrieved chunks; the matching page is 6th, outside top-5.
    retrieved = [_chunk(p, "x") for p in [1, 2, 3, 4, 5, 6]]

    result = score_entry(entry, retrieved)

    assert result.recall_at_5 == 0.0


# ----------------------------------------------------------------- aggregate_metrics


def test_aggregate_metrics_averages_each_family_separately() -> None:
    results = [
        EntryResult(
            id="a1",
            question="q",
            must_refuse=False,
            retrieved_pages=[1],
            recall_at_5=1.0,
            keyword_hit=0.5,
            refusal_correct=None,
        ),
        EntryResult(
            id="a2",
            question="q",
            must_refuse=False,
            retrieved_pages=[],
            recall_at_5=0.0,
            keyword_hit=0.0,
            refusal_correct=None,
        ),
        EntryResult(
            id="r1",
            question="q",
            must_refuse=True,
            retrieved_pages=[],
            recall_at_5=None,
            keyword_hit=None,
            refusal_correct=True,
        ),
        EntryResult(
            id="r2",
            question="q",
            must_refuse=True,
            retrieved_pages=[1],
            recall_at_5=None,
            keyword_hit=None,
            refusal_correct=False,
        ),
    ]

    metrics = aggregate_metrics(results)

    assert metrics.recall_at_5 == pytest.approx(0.5)
    assert metrics.keyword_hit == pytest.approx(0.25)
    assert metrics.refusal_accuracy == pytest.approx(0.5)


def test_aggregate_metrics_raises_without_answerable_entries() -> None:
    only_refusals = [
        EntryResult(
            id="r1",
            question="q",
            must_refuse=True,
            retrieved_pages=[],
            recall_at_5=None,
            keyword_hit=None,
            refusal_correct=True,
        )
    ]

    with pytest.raises(ValueError, match="answerable"):
        aggregate_metrics(only_refusals)


def test_aggregate_metrics_raises_without_refusal_entries() -> None:
    only_answerable = [
        EntryResult(
            id="a1",
            question="q",
            must_refuse=False,
            retrieved_pages=[1],
            recall_at_5=1.0,
            keyword_hit=1.0,
            refusal_correct=None,
        )
    ]

    with pytest.raises(ValueError, match="must_refuse"):
        aggregate_metrics(only_answerable)
