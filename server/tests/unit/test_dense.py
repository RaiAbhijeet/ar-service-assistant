"""Unit tests for app.retrieval.dense.

embed_query is tested against a faked Ollama (httpx.MockTransport, like
ingest/embed.py's tests) — no real network. search_dense is tested against
a real local Postgres+pgvector (see conftest.py's pg_conn — skips if
unreachable) since pgvector's cosine-distance math can't be meaningfully
faked.
"""

import json
from collections.abc import Awaitable, Callable

import asyncpg
import httpx
import pytest

from app.retrieval.dense import EmbedQueryError, embed_query, search_dense

# Matches conftest.py's _TEST_OBJECT_ID. Duplicated as a literal rather than
# imported: tests/ isn't a package (no __init__.py — pytest's own rootless
# collection doesn't need one, but a cross-file `import` does).
_TEST_OBJECT_ID = "test-retrieval-fixture"


def _fixed_vector(**dims: float) -> list[float]:
    """A 1024-dim vector (matches schema.sql's vector(1024)), zero except at `dims`."""
    vector = [0.0] * 1024
    for index, value in dims.items():
        vector[int(index)] = value
    return vector


async def test_embed_query_returns_the_single_vector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["input"] == ["Sieb verstopft"]
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vector = await embed_query(
            "Sieb verstopft", ollama_host="http://x", model="bge-m3", client=client
        )

    assert vector == [0.1, 0.2, 0.3]


async def test_embed_query_raises_on_missing_embeddings() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmbedQueryError, match="expected exactly one vector"):
            await embed_query("x", ollama_host="http://x", model="bge-m3", client=client)


async def test_search_dense_orders_by_cosine_similarity(
    pg_conn: asyncpg.Connection, insert_chunk: Callable[..., Awaitable[int]]
) -> None:
    await insert_chunk(text="Naechster Treffer", embedding=_fixed_vector(**{"0": 0.8, "1": 0.6}))
    await insert_chunk(text="Bester Treffer", embedding=_fixed_vector(**{"0": 1.0}))
    await insert_chunk(text="Kein Treffer", embedding=_fixed_vector(**{"1": 1.0}))

    results = await search_dense(
        pg_conn,
        object_id=_TEST_OBJECT_ID,
        query_vector=_fixed_vector(**{"0": 1.0}),
        top_k=10,
    )

    assert [r.text for r in results] == ["Bester Treffer", "Naechster Treffer", "Kein Treffer"]
    assert results[0].dense_score == pytest.approx(1.0)
    assert results[1].dense_score == pytest.approx(0.8)
    assert results[2].dense_score == pytest.approx(0.0, abs=1e-6)


async def test_search_dense_respects_top_k(
    pg_conn: asyncpg.Connection, insert_chunk: Callable[..., Awaitable[int]]
) -> None:
    for i in range(5):
        await insert_chunk(text=f"chunk {i}", embedding=_fixed_vector(**{str(i): 1.0}))

    results = await search_dense(
        pg_conn,
        object_id=_TEST_OBJECT_ID,
        query_vector=_fixed_vector(**{"0": 1.0}),
        top_k=2,
    )

    assert len(results) == 2


async def test_search_dense_ignores_other_objects(
    pg_conn: asyncpg.Connection, insert_chunk: Callable[..., Awaitable[int]]
) -> None:
    await insert_chunk(
        text="Anderes Objekt",
        embedding=_fixed_vector(**{"0": 1.0}),
        object_id="test-other-object",
    )

    results = await search_dense(
        pg_conn,
        object_id=_TEST_OBJECT_ID,
        query_vector=_fixed_vector(**{"0": 1.0}),
        top_k=10,
    )

    assert results == []
