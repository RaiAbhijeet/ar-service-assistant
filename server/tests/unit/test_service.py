"""Unit tests for app.retrieval.service.

No real network/DB: embed_query, search_dense and search_lexical are
monkeypatched at the point of use in app.retrieval.service — the same
pattern already used by test_health.py for asyncpg.connect.
"""

from typing import Any

import pytest

import app.retrieval.service as service_module
from app.retrieval.models import RetrievedChunk
from app.retrieval.service import RetrievalService


def _chunk(id_: int, **scores: float) -> RetrievedChunk:
    return RetrievedChunk(
        id=id_,
        object_id="obj",
        manual_id="man",
        page=1,
        section="Sec",
        step_no=None,
        text=f"chunk {id_}",
        figure_ids=[],
        **scores,
    )


class _FakeAcquireCtx:
    async def __aenter__(self) -> str:
        return "fake-conn"

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakePool:
    def acquire(self) -> _FakeAcquireCtx:
        return _FakeAcquireCtx()


def _service(**overrides: Any) -> RetrievalService:
    kwargs: dict[str, Any] = {
        "pool": _FakePool(),
        "ollama_host": "http://x",
        "embed_model": "bge-m3",
        "min_retrieval_score": 0.35,
    }
    kwargs.update(overrides)
    return RetrievalService(**kwargs)


async def _fake_embed_query(*_args: object, **_kwargs: object) -> list[float]:
    return [0.1, 0.2]


async def test_search_returns_fused_results_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_dense(*_args: object, **_kwargs: object) -> list[RetrievedChunk]:
        return [_chunk(1, dense_score=0.9), _chunk(2, dense_score=0.5)]

    async def fake_search_lexical(*_args: object, **_kwargs: object) -> list[RetrievedChunk]:
        return [_chunk(2, lexical_score=0.8)]

    monkeypatch.setattr(service_module, "embed_query", _fake_embed_query)
    monkeypatch.setattr(service_module, "search_dense", fake_search_dense)
    monkeypatch.setattr(service_module, "search_lexical", fake_search_lexical)

    results = await _service().search("Sieb verstopft", object_id="obj", top_k=10)

    # chunk 2 is found by both dense (rank 2) and lexical (rank 1), so its
    # fused RRF score beats chunk 1 (found by dense alone, rank 1).
    assert [r.id for r in results] == [2, 1]
    assert results[0].dense_score == 0.5
    assert results[0].lexical_score == 0.8


async def test_search_returns_empty_below_threshold_and_skips_lexical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lexical_called = False

    async def fake_search_dense(*_args: object, **_kwargs: object) -> list[RetrievedChunk]:
        return [_chunk(1, dense_score=0.1)]  # below the 0.35 default threshold

    async def fake_search_lexical(*_args: object, **_kwargs: object) -> list[RetrievedChunk]:
        nonlocal lexical_called
        lexical_called = True
        return []

    monkeypatch.setattr(service_module, "embed_query", _fake_embed_query)
    monkeypatch.setattr(service_module, "search_dense", fake_search_dense)
    monkeypatch.setattr(service_module, "search_lexical", fake_search_lexical)

    results = await _service().search("irrelevant query", object_id="obj", top_k=10)

    assert results == []
    assert lexical_called is False


async def test_search_returns_empty_when_no_dense_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_dense(*_args: object, **_kwargs: object) -> list[RetrievedChunk]:
        return []

    monkeypatch.setattr(service_module, "embed_query", _fake_embed_query)
    monkeypatch.setattr(service_module, "search_dense", fake_search_dense)

    results = await _service().search("query", object_id="obj", top_k=10)

    assert results == []


async def test_search_respects_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_dense(*_args: object, **_kwargs: object) -> list[RetrievedChunk]:
        return [_chunk(i, dense_score=0.9) for i in range(5)]

    async def fake_search_lexical(*_args: object, **_kwargs: object) -> list[RetrievedChunk]:
        return []

    monkeypatch.setattr(service_module, "embed_query", _fake_embed_query)
    monkeypatch.setattr(service_module, "search_dense", fake_search_dense)
    monkeypatch.setattr(service_module, "search_lexical", fake_search_lexical)

    results = await _service().search("query", object_id="obj", top_k=2)

    assert len(results) == 2
