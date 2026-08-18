"""Unit tests for ingest.embed.

No real network or database (CLAUDE.md section 7): Ollama is faked via an
httpx.MockTransport injected through embed_chunks' `client` parameter;
Postgres is faked with a minimal in-memory stand-in for asyncpg.Connection.
"""

import json

import httpx
import pytest

import ingest.embed as embed_module
from ingest.chunk import Chunk
from ingest.embed import EmbedError, embed_chunks, store_chunks


def _chunk(text: str, *, object_id: str = "obj", manual_id: str = "man", page: int = 1) -> Chunk:
    return Chunk(
        object_id=object_id, manual_id=manual_id, page=page, section="Sec", step_no=None, text=text
    )


def _echo_dim_client(dim: int = 4) -> httpx.AsyncClient:
    """Fake Ollama /api/embed: returns `dim`-length vectors, one per input."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        n = len(body["input"])
        return httpx.Response(200, json={"embeddings": [[0.1] * dim for _ in range(n)]})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class _FakeTransaction:
    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction()

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def executemany(self, query: str, args_list: list[tuple[object, ...]]) -> None:
        self.executemany_calls.append((query, list(args_list)))


async def test_embed_chunks_returns_empty_list_for_no_chunks() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call Ollama for an empty chunk list")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vectors = await embed_chunks([], ollama_host="http://x", model="bge-m3", client=client)

    assert vectors == []


async def test_embed_chunks_returns_one_vector_per_chunk_in_order() -> None:
    chunks = [_chunk("eins"), _chunk("zwei"), _chunk("drei")]
    async with _echo_dim_client(dim=4) as client:
        vectors = await embed_chunks(chunks, ollama_host="http://x", model="bge-m3", client=client)

    assert len(vectors) == 3
    assert all(len(v) == 4 for v in vectors)


async def test_embed_chunks_batches_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embed_module, "_BATCH_SIZE", 2)
    requests_seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests_seen.append(len(body["input"]))
        return httpx.Response(200, json={"embeddings": [[0.0] for _ in body["input"]]})

    chunks = [_chunk(str(i)) for i in range(5)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vectors = await embed_chunks(chunks, ollama_host="http://x", model="bge-m3", client=client)

    assert requests_seen == [2, 2, 1]  # 5 chunks at batch size 2 -> three requests
    assert len(vectors) == 5


async def test_embed_chunks_raises_on_mismatched_embedding_count() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})  # 1 for 2 inputs

    chunks = [_chunk("eins"), _chunk("zwei")]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmbedError, match="1 embeddings for a batch of 2"):
            await embed_chunks(chunks, ollama_host="http://x", model="bge-m3", client=client)


async def test_embed_chunks_raises_on_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "model not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await embed_chunks(
                [_chunk("eins")], ollama_host="http://x", model="bge-m3", client=client
            )


async def test_store_chunks_deletes_then_inserts() -> None:
    chunks = [
        _chunk("eins", object_id="siemens-dishwasher"),
        _chunk("zwei", object_id="siemens-dishwasher"),
    ]
    vectors = [[0.1, 0.2], [0.3, 0.4]]
    conn = _FakeConnection()

    await store_chunks(chunks, vectors, object_id="siemens-dishwasher", conn=conn)  # type: ignore[arg-type]

    assert len(conn.executed) == 1
    delete_query, delete_args = conn.executed[0]
    assert "DELETE FROM chunks" in delete_query
    assert delete_args == ("siemens-dishwasher",)

    assert len(conn.executemany_calls) == 1
    insert_query, rows = conn.executemany_calls[0]
    assert "INSERT INTO chunks" in insert_query
    assert len(rows) == 2
    assert rows[0][0] == "siemens-dishwasher"  # object_id is the first column
    assert rows[0][-1] == [0.1, 0.2]  # embedding is the last column


async def test_store_chunks_raises_on_length_mismatch() -> None:
    conn = _FakeConnection()
    with pytest.raises(EmbedError, match="2 chunks but 1 vectors"):
        await store_chunks(
            [_chunk("eins"), _chunk("zwei")],
            [[0.1]],
            object_id="obj",
            conn=conn,  # type: ignore[arg-type]
        )
