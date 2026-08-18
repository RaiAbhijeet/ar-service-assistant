"""Downloads and verifies each manual listed in an object's manifest.

Per CLAUDE.md section 2, this is the one place in the codebase allowed to
make outbound internet requests — and only at ingest time, never from
`app/`. Every downloaded file is hash-verified against `object.yaml` before
it's trusted; a mismatch deletes the file and refuses to continue rather
than silently using an unverified manual.
"""

import hashlib
from pathlib import Path

import httpx

from app.telemetry.logging import get_logger
from ingest.manifest import ManualSource

logger = get_logger()

_CHUNK_SIZE = 1024 * 1024  # 1 MiB
_DEFAULT_TIMEOUT_S = 60.0


class HashMismatchError(RuntimeError):
    """Raised when a downloaded file's SHA-256 doesn't match object.yaml."""


def download_manual(
    manual: ManualSource,
    dest_dir: Path,
    *,
    client: httpx.Client | None = None,
) -> Path:
    """Download `manual` into `dest_dir/<manual.id>.pdf`, verifying its hash.

    Reuses an existing file in place if it's already present and already
    matches the expected hash, so re-running ingestion doesn't re-download
    every manual. Raises `HashMismatchError` (and deletes the bad file) if
    the downloaded bytes don't match — nothing unverified is ever kept.

    `client` is injectable so callers can share one `httpx.Client` across
    multiple manuals (see `download_all`) and so tests can pass a client
    wired to a fake transport instead of hitting the network.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{manual.id}.pdf"

    if dest_path.is_file() and _sha256_of(dest_path) == manual.sha256:
        logger.info("ingest.download.cached", manual_id=manual.id, path=str(dest_path))
        return dest_path

    logger.info("ingest.download.start", manual_id=manual.id, url=str(manual.url))
    owns_client = client is None
    http_client = (
        client
        if client is not None
        else httpx.Client(timeout=_DEFAULT_TIMEOUT_S, follow_redirects=True)
    )
    try:
        with http_client.stream("GET", str(manual.url)) as response:
            response.raise_for_status()
            with dest_path.open("wb") as f:
                for data in response.iter_bytes(_CHUNK_SIZE):
                    f.write(data)
    finally:
        if owns_client:
            http_client.close()

    actual = _sha256_of(dest_path)
    if actual != manual.sha256:
        dest_path.unlink(missing_ok=True)
        raise HashMismatchError(
            f"SHA-256 mismatch for manual '{manual.id}' downloaded from {manual.url}: "
            f"expected {manual.sha256}, got {actual}. Refusing to use this file — it may "
            f"be the wrong revision or a corrupted download. Nothing was kept on disk."
        )

    logger.info("ingest.download.verified", manual_id=manual.id, path=str(dest_path))
    return dest_path


def download_all(
    manuals: list[ManualSource],
    dest_dir: Path,
    *,
    client: httpx.Client | None = None,
) -> list[Path]:
    """Download and verify every manual, returning their local paths in order."""
    owns_client = client is None
    http_client = (
        client
        if client is not None
        else httpx.Client(timeout=_DEFAULT_TIMEOUT_S, follow_redirects=True)
    )
    try:
        return [download_manual(manual, dest_dir, client=http_client) for manual in manuals]
    finally:
        if owns_client:
            http_client.close()


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
