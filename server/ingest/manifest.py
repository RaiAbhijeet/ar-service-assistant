"""Parses the ingestion-relevant subset of an object's `object.yaml`.

Ingestion only needs the object id and its `manuals[]` list — parts,
thresholds, the capture plan and safety prompts belong to other modules
(vision, retrieval, orchestrator) and are deliberately not modelled here.
`extra="ignore"` lets this module coexist with the rest of `object.yaml`
without needing to know its full schema.
"""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ManualSource(BaseModel):
    """One entry under `manuals:` in `object.yaml`."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title_de: str
    url: HttpUrl
    sha256: str
    language: str

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        """Reject anything that isn't a real 64-char hex digest.

        This also catches an un-filled-in `<PASTE sha256 OF THAT FILE>`
        placeholder early, with a clearer message than a downstream hash
        mismatch would give.
        """
        normalized = value.lower()
        if not _SHA256_RE.match(normalized):
            raise ValueError(
                f"sha256 must be a 64-character hex string, got {value!r}. "
                "Did you forget to replace the <PLACEHOLDER> in object.yaml?"
            )
        return normalized


class ObjectManifest(BaseModel):
    """The ingestion-relevant subset of `object.yaml`."""

    model_config = ConfigDict(extra="ignore")

    id: str
    manuals: list[ManualSource]


def load_manifest(objects_dir: Path, object_id: str) -> ObjectManifest:
    """Load and validate `<objects_dir>/<object_id>/object.yaml`.

    Raises `FileNotFoundError` if the object folder or its `object.yaml` is
    missing, and `pydantic.ValidationError` if required fields (e.g. a
    still-`<PLACEHOLDER>` sha256/url) are missing or malformed.
    """
    path = objects_dir / object_id / "object.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"No object.yaml found for '{object_id}' at {path}. "
            f"Check --object matches a folder name under {objects_dir}."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ObjectManifest.model_validate(raw)
