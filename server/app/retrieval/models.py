"""Data model for a retrieved chunk.

Mirrors a row of the `chunks` table (see `ingest/schema.sql`) plus
retrieval scoring. Deliberately separate from `ingest.chunk.Chunk`: that
type is a pre-embedding processing artifact (no id, no embedding, no
score); this one is what retrieval actually returns to a caller.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    """One chunk, as returned by hybrid retrieval.

    Scores are kept separate rather than blended into one number: the
    empty-result threshold decision (service.py) uses `dense_score`
    specifically, while display order uses `fused_score` — collapsing them
    into one field would make it impossible to tell which one a caller is
    looking at.
    """

    id: int
    object_id: str
    manual_id: str
    page: int
    section: str
    step_no: int | None
    text: str
    figure_ids: list[str]

    dense_score: float | None = None
    lexical_score: float | None = None
    fused_score: float | None = None


def chunk_from_row(row: Mapping[str, Any], **scores: float | None) -> RetrievedChunk:
    """Build a `RetrievedChunk` from a `chunks` table row plus scoring fields."""
    return RetrievedChunk(
        id=row["id"],
        object_id=row["object_id"],
        manual_id=row["manual_id"],
        page=row["page"],
        section=row["section"],
        step_no=row["step_no"],
        text=row["text"],
        figure_ids=list(row["figure_ids"]),
        **scores,
    )
