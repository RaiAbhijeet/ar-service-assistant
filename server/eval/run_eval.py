"""CLI entrypoint: `python -m eval.run_eval --object <id> --report <path>`.

For every entry in `golden_de.yaml`, runs it through the real hybrid
`RetrievalService` (same code path the orchestrator uses) and scores the
result. Talks only to the local Postgres and Ollama — no cloud call, per
CLAUDE.md section 2.

Metric definitions (see `docs/reference-abi/IMPLEMENTATION-GUIDE-M0-M7.md`,
M1.3):

- `recall_at_5`   — for answerable entries, the fraction of `expected_pages`
  that appear among the top-5 retrieved chunks' pages.
- `keyword_hit`   — for answerable entries, the fraction of
  `expected_keywords` present (case-insensitive substring) in the retrieved
  chunks' text.
- `refusal_correct` — for `must_refuse` entries, whether retrieval returned
  an empty list.

`recall_at_5` and `keyword_hit` are undefined (`null`) for `must_refuse`
entries — there is no correct chunk to score against. `refusal_correct` is
undefined (`null`) for answerable entries — refusing isn't the desired
outcome there, and would already show up as `recall_at_5: 0.0`.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
from pydantic import BaseModel

from app.config import get_settings
from app.retrieval.models import RetrievedChunk
from app.retrieval.service import RetrievalService
from app.telemetry.logging import configure_logging, get_logger
from eval.schema import GoldenEntry, GoldenSetError, load_golden_set

logger = get_logger()

# recall_at_5 is scored against exactly the top 5 fused results — not a
# tunable knob, since a different top_k would make the metric name a lie.
TOP_K = 5

_GOLDEN_PATH = Path(__file__).parent / "golden_de.yaml"


class EntryResult(BaseModel):
    """Per-entry scoring, included in the report for auditability."""

    id: str
    question: str
    must_refuse: bool
    retrieved_pages: list[int]
    recall_at_5: float | None
    keyword_hit: float | None
    refusal_correct: bool | None


class EvalMetrics(BaseModel):
    """Report-level aggregates, the numbers `check_thresholds.py` gates on."""

    recall_at_5: float
    keyword_hit: float
    refusal_accuracy: float


class EvalReport(BaseModel):
    """The full JSON report written to `--report`."""

    object_id: str
    generated_at: str
    golden_set_path: str
    n_entries: int
    n_answerable: int
    n_must_refuse: int
    metrics: EvalMetrics
    entries: list[EntryResult]


def _recall_at_5(expected_pages: Sequence[int], retrieved_pages: Sequence[int]) -> float:
    """Fraction of `expected_pages` covered by the top-5 retrieved pages."""
    top5 = set(retrieved_pages[:TOP_K])
    hits = len(set(expected_pages) & top5)
    return hits / len(set(expected_pages))


def _keyword_hit(expected_keywords: Sequence[str], retrieved_text: str) -> float:
    """Fraction of `expected_keywords` found (case-insensitive) in the retrieved text."""
    if not expected_keywords:
        return 1.0
    text_lower = retrieved_text.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in text_lower)
    return hits / len(expected_keywords)


def score_entry(entry: GoldenEntry, retrieved: Sequence[RetrievedChunk]) -> EntryResult:
    """Score one golden entry against what retrieval actually returned."""
    retrieved_pages = [chunk.page for chunk in retrieved]

    if entry.must_refuse:
        return EntryResult(
            id=entry.id,
            question=entry.question,
            must_refuse=True,
            retrieved_pages=retrieved_pages,
            recall_at_5=None,
            keyword_hit=None,
            refusal_correct=len(retrieved) == 0,
        )

    retrieved_text = "\n".join(chunk.text for chunk in retrieved)
    return EntryResult(
        id=entry.id,
        question=entry.question,
        must_refuse=False,
        retrieved_pages=retrieved_pages,
        recall_at_5=_recall_at_5(entry.expected_pages, retrieved_pages),
        keyword_hit=_keyword_hit(entry.expected_keywords, retrieved_text),
        refusal_correct=None,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def aggregate_metrics(results: Sequence[EntryResult]) -> EvalMetrics:
    """Roll per-entry scores up into the report-level metrics.

    Raises `ValueError` if the golden set has no entries of one of the two
    kinds — each metric needs at least one entry to average over, and a
    golden set that's entirely one kind can't exercise both retrieval
    behaviours the system is required to have (CLAUDE.md section 2).
    """
    answerable = [r for r in results if not r.must_refuse]
    refusals = [r for r in results if r.must_refuse]
    if not answerable:
        raise ValueError(
            "golden set has no answerable (must_refuse: false) entries — "
            "recall_at_5 and keyword_hit can't be scored."
        )
    if not refusals:
        raise ValueError(
            "golden set has no must_refuse entries — refusal_accuracy can't be scored."
        )

    return EvalMetrics(
        recall_at_5=_mean([r.recall_at_5 for r in answerable if r.recall_at_5 is not None]),
        keyword_hit=_mean([r.keyword_hit for r in answerable if r.keyword_hit is not None]),
        refusal_accuracy=_mean([1.0 if r.refusal_correct else 0.0 for r in refusals]),
    )


async def run_eval(*, object_id: str, golden_path: Path, report_path: Path) -> EvalReport:
    """Run every golden entry through retrieval, score it, and write the report."""
    entries = load_golden_set(golden_path)
    settings = get_settings()

    # No register_vector() here: RetrievalService never stores or decodes a
    # `vector` column value, only compares against one via a text-cast
    # literal (see dense.py's search_dense) — deliberately so it works on a
    # plain pool connection with no per-connection codec setup.
    pool = await asyncpg.create_pool(dsn=settings.database_dsn)
    try:
        service = RetrievalService(
            pool=pool,
            ollama_host=settings.ollama_host,
            embed_model=settings.arsa_embed_model,
            min_retrieval_score=settings.arsa_min_retrieval_score,
        )
        results: list[EntryResult] = []
        for entry in entries:
            retrieved = await service.search(entry.question, object_id=object_id, top_k=TOP_K)
            results.append(score_entry(entry, retrieved))
            logger.info(
                "eval.entry",
                id=entry.id,
                must_refuse=entry.must_refuse,
                n_retrieved=len(retrieved),
            )
    finally:
        await pool.close()

    metrics = aggregate_metrics(results)
    report = EvalReport(
        object_id=object_id,
        generated_at=datetime.now(UTC).isoformat(),
        golden_set_path=str(golden_path),
        n_entries=len(entries),
        n_answerable=sum(1 for e in entries if not e.must_refuse),
        n_must_refuse=sum(1 for e in entries if e.must_refuse),
        metrics=metrics,
        entries=results,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    logger.info("eval.done", object_id=object_id, report=str(report_path), **metrics.model_dump())
    return report


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Run golden_de.yaml through retrieval and write a JSON eval report."
    )
    parser.add_argument("--object", required=True, help="Object id (a folder name under objects/).")
    parser.add_argument(
        "--report", required=True, type=Path, help="Path to write the JSON report to."
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=_GOLDEN_PATH,
        help=f"Path to golden_de.yaml (default: {_GOLDEN_PATH}).",
    )
    args = parser.parse_args()

    try:
        report = asyncio.run(
            run_eval(object_id=args.object, golden_path=args.golden, report_path=args.report)
        )
    except GoldenSetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Wrote eval report to {args.report}")
    print(
        f"recall_at_5={report.metrics.recall_at_5:.3f} "
        f"keyword_hit={report.metrics.keyword_hit:.3f} "
        f"refusal_accuracy={report.metrics.refusal_accuracy:.3f}"
    )


if __name__ == "__main__":
    main()
