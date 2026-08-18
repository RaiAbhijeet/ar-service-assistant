"""Unit tests for ingest.manifest. No network, filesystem limited to tmp_path."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ingest.manifest import load_manifest

_VALID_SHA256 = "a" * 64
_VALID_YAML = f"""
id: test-object
manuals:
  - id: gebrauchsanleitung
    title_de: "Testhandbuch"
    url: "https://example.invalid/manual.pdf"
    sha256: "{_VALID_SHA256}"
    language: de
# Ingestion must ignore everything below `manuals` — it isn't its concern.
parts:
  - id: some_part
    name_de: Irgendein Teil
"""


def _write_object_yaml(objects_dir: Path, object_id: str, content: str) -> None:
    obj_dir = objects_dir / object_id
    obj_dir.mkdir(parents=True)
    (obj_dir / "object.yaml").write_text(content, encoding="utf-8")


def test_load_manifest_parses_manuals_and_ignores_other_sections(tmp_path: Path) -> None:
    _write_object_yaml(tmp_path, "test-object", _VALID_YAML)

    manifest = load_manifest(tmp_path, "test-object")

    assert manifest.id == "test-object"
    assert len(manifest.manuals) == 1
    assert manifest.manuals[0].id == "gebrauchsanleitung"
    assert manifest.manuals[0].sha256 == _VALID_SHA256


def test_load_manifest_missing_object_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="test-object"):
        load_manifest(tmp_path, "test-object")


def test_load_manifest_rejects_placeholder_sha256(tmp_path: Path) -> None:
    bad_yaml = _VALID_YAML.replace(_VALID_SHA256, "<PASTE sha256 OF THAT FILE>")
    _write_object_yaml(tmp_path, "test-object", bad_yaml)

    with pytest.raises(ValidationError, match="sha256"):
        load_manifest(tmp_path, "test-object")


def test_load_manifest_rejects_placeholder_url(tmp_path: Path) -> None:
    bad_yaml = _VALID_YAML.replace("https://example.invalid/manual.pdf", "<PASTE THE PUBLIC URL>")
    _write_object_yaml(tmp_path, "test-object", bad_yaml)

    with pytest.raises(ValidationError):
        load_manifest(tmp_path, "test-object")


def test_load_manifest_normalizes_sha256_to_lowercase(tmp_path: Path) -> None:
    upper_yaml = _VALID_YAML.replace(_VALID_SHA256, _VALID_SHA256.upper())
    _write_object_yaml(tmp_path, "test-object", upper_yaml)

    manifest = load_manifest(tmp_path, "test-object")

    assert manifest.manuals[0].sha256 == _VALID_SHA256
