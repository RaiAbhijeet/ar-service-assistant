"""Parses and validates `golden_de.yaml`.

`golden_de.yaml` is written by hand by the repo owner (CLAUDE.md section 6.6)
and never by this codebase — this module only ever reads it. Validation is
deliberately strict: a golden set that silently tolerates a malformed entry
would make the eval report a number nobody can trust.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class GoldenEntry(BaseModel):
    """One entry in `golden_de.yaml`.

    The two families of entry are mutually exclusive by construction: an
    answerable entry (`must_refuse: false`) must name at least one page the
    answer lives on, so `recall_at_5` has something to score against; a
    refusal entry (`must_refuse: true`) must name none, since there is no
    "correct" chunk to retrieve — the correct behaviour is retrieving
    nothing at all (ADR-0006).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    expected_pages: list[int]
    expected_keywords: list[str]
    must_refuse: bool

    @model_validator(mode="after")
    def _check_pages_and_keywords_match_must_refuse(self) -> "GoldenEntry":
        if self.must_refuse:
            if self.expected_pages or self.expected_keywords:
                raise ValueError(
                    f"{self.id}: must_refuse entries must have empty "
                    "expected_pages and expected_keywords — there is no "
                    "correct chunk for the system to retrieve here."
                )
        elif not self.expected_pages:
            raise ValueError(
                f"{self.id}: answerable entries (must_refuse: false) need at "
                "least one expected_pages entry, or recall_at_5 can't be scored."
            )
        return self


class GoldenSetError(ValueError):
    """Raised when `golden_de.yaml` is missing or fails validation."""


def load_golden_set(path: Path) -> list[GoldenEntry]:
    """Load and validate every entry in `golden_de.yaml` at `path`.

    Raises `GoldenSetError` — with a message pointing at what to fix — if
    the file is missing, isn't a list of mappings, contains a malformed
    entry, or reuses an `id`. Never writes to `path`.
    """
    if not path.is_file():
        raise GoldenSetError(
            f"No golden set found at {path}. golden_de.yaml is written by hand "
            "by the repo owner — see CLAUDE.md section 6.6. Write it before "
            "running the eval harness."
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise GoldenSetError(
            f"{path} must contain a YAML list of entries, got {type(raw).__name__}."
        )

    entries: list[GoldenEntry] = []
    seen_ids: set[str] = set()
    for i, raw_entry in enumerate(raw):
        try:
            entry = GoldenEntry.model_validate(raw_entry)
        except Exception as exc:
            raise GoldenSetError(f"{path}, entry {i}: {exc}") from exc
        if entry.id in seen_ids:
            raise GoldenSetError(f"{path}: duplicate entry id {entry.id!r}.")
        seen_ids.add(entry.id)
        entries.append(entry)

    if not entries:
        raise GoldenSetError(f"{path} contains no entries.")

    return entries
