"""Unit tests for ingest.download.

No real network calls (CLAUDE.md section 7): httpx.Client is wired to an
httpx.MockTransport and injected via download_manual's `client` parameter
rather than monkeypatched.
"""

import hashlib
from pathlib import Path

import httpx
import pytest

from ingest.download import HashMismatchError, download_all, download_manual
from ingest.manifest import ManualSource

_CONTENT = b"%PDF-1.4 fake manual content for testing\n"
_CONTENT_HASH = hashlib.sha256(_CONTENT).hexdigest()


def _manual(manual_id: str = "test-manual", sha256: str = _CONTENT_HASH) -> ManualSource:
    return ManualSource(
        id=manual_id,
        title_de="Testhandbuch",
        url=f"https://example.invalid/{manual_id}.pdf",
        sha256=sha256,
        language="de",
    )


def _client_returning(content: bytes, status: int = 200) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_manual_verifies_matching_hash(tmp_path: Path) -> None:
    with _client_returning(_CONTENT) as client:
        result = download_manual(_manual(), tmp_path, client=client)

    assert result == tmp_path / "test-manual.pdf"
    assert result.read_bytes() == _CONTENT


def test_download_manual_refuses_on_hash_mismatch(tmp_path: Path) -> None:
    wrong_hash = "0" * 64
    with (
        _client_returning(_CONTENT) as client,
        pytest.raises(HashMismatchError, match="SHA-256 mismatch"),
    ):
        download_manual(_manual(sha256=wrong_hash), tmp_path, client=client)

    assert not (tmp_path / "test-manual.pdf").exists()


def test_download_manual_raises_on_http_error(tmp_path: Path) -> None:
    with _client_returning(b"", status=404) as client, pytest.raises(httpx.HTTPStatusError):
        download_manual(_manual(), tmp_path, client=client)

    assert not (tmp_path / "test-manual.pdf").exists()


def test_download_manual_reuses_cached_file_with_matching_hash(tmp_path: Path) -> None:
    dest = tmp_path / "test-manual.pdf"
    dest.write_bytes(_CONTENT)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not re-download a file that already matches its hash")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = download_manual(_manual(), tmp_path, client=client)

    assert result == dest


def test_download_manual_redownloads_cached_file_with_wrong_hash(tmp_path: Path) -> None:
    dest = tmp_path / "test-manual.pdf"
    dest.write_bytes(b"stale content that doesn't match the expected hash")

    with _client_returning(_CONTENT) as client:
        result = download_manual(_manual(), tmp_path, client=client)

    assert result.read_bytes() == _CONTENT


def test_download_all_downloads_every_manual_in_order(tmp_path: Path) -> None:
    manuals = [_manual("first"), _manual("second")]

    with _client_returning(_CONTENT) as client:
        paths = download_all(manuals, tmp_path, client=client)

    assert paths == [tmp_path / "first.pdf", tmp_path / "second.pdf"]
    assert all(p.read_bytes() == _CONTENT for p in paths)
