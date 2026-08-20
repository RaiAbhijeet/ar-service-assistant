"""Unit tests for eval.schema. No network, filesystem limited to tmp_path."""

from pathlib import Path

import pytest

from eval.schema import GoldenSetError, load_golden_set

_VALID_YAML = """
- id: g001
  question: "Wie stelle ich die Wasserhaerte ein?"
  expected_pages: [25, 26]
  expected_keywords: ["Enthaertungsanlage", "H04"]
  must_refuse: false

- id: g002
  question: "Wie lange ist die Garantie?"
  expected_pages: []
  expected_keywords: []
  must_refuse: true
"""


def _write_golden(tmp_path: Path, content: str, name: str = "golden_de.yaml") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_golden_set_parses_valid_entries(tmp_path: Path) -> None:
    path = _write_golden(tmp_path, _VALID_YAML)

    entries = load_golden_set(path)

    assert [e.id for e in entries] == ["g001", "g002"]
    assert entries[0].must_refuse is False
    assert entries[1].must_refuse is True


def test_missing_file_raises_clear_message_pointing_at_hand_authoring(tmp_path: Path) -> None:
    path = tmp_path / "golden_de.yaml"

    with pytest.raises(GoldenSetError, match="written by hand"):
        load_golden_set(path)


def test_rejects_must_refuse_entry_with_expected_pages(tmp_path: Path) -> None:
    bad = _VALID_YAML.replace(
        "  expected_pages: []\n  expected_keywords: []\n  must_refuse: true",
        "  expected_pages: [1]\n  expected_keywords: []\n  must_refuse: true",
    )
    path = _write_golden(tmp_path, bad)

    with pytest.raises(GoldenSetError, match="must_refuse"):
        load_golden_set(path)


def test_rejects_answerable_entry_with_no_expected_pages(tmp_path: Path) -> None:
    bad = _VALID_YAML.replace(
        '  expected_pages: [25, 26]\n  expected_keywords: ["Enthaertungsanlage", "H04"]\n'
        "  must_refuse: false",
        '  expected_pages: []\n  expected_keywords: ["Enthaertungsanlage", "H04"]\n'
        "  must_refuse: false",
    )
    path = _write_golden(tmp_path, bad)

    with pytest.raises(GoldenSetError, match="expected_pages"):
        load_golden_set(path)


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    duplicated = _VALID_YAML + _VALID_YAML
    path = _write_golden(tmp_path, duplicated)

    with pytest.raises(GoldenSetError, match="duplicate"):
        load_golden_set(path)


def test_rejects_non_list_top_level(tmp_path: Path) -> None:
    path = _write_golden(tmp_path, "id: not-a-list\n")

    with pytest.raises(GoldenSetError, match="list"):
        load_golden_set(path)


def test_rejects_unknown_field(tmp_path: Path) -> None:
    bad = _VALID_YAML.replace("  must_refuse: false", "  must_refuse: false\n  extra_field: oops")
    path = _write_golden(tmp_path, bad)

    with pytest.raises(GoldenSetError):
        load_golden_set(path)
