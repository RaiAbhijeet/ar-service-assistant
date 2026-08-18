"""Unit tests for app.retrieval.lexical.

Real local Postgres (see conftest.py's pg_conn — skips if unreachable):
Postgres' German full-text ranking can't be meaningfully faked.
"""

from collections.abc import Awaitable, Callable

import asyncpg

from app.retrieval.lexical import search_lexical

# Matches conftest.py's TEST_OBJECT_ID. Duplicated as a literal rather than
# imported: tests/ isn't a package (no __init__.py).
_TEST_OBJECT_ID = "test-retrieval-fixture"


async def test_search_lexical_ranks_matching_chunk_first(
    pg_conn: asyncpg.Connection, insert_chunk: Callable[..., Awaitable[int]]
) -> None:
    await insert_chunk(text="Siebe sind verschmutzt oder verstopft.")
    await insert_chunk(text="Die Abwasserpumpe muss bei Blockaden gereinigt werden.")
    await insert_chunk(text="Stellen Sie das Gerät auf eine ebene Fläche.")

    results = await search_lexical(
        pg_conn, object_id=_TEST_OBJECT_ID, query="Sieb verstopft", top_k=10
    )

    assert len(results) == 1
    assert "Siebe" in results[0].text
    assert results[0].lexical_score is not None
    assert results[0].lexical_score > 0


async def test_search_lexical_returns_empty_for_no_match(
    pg_conn: asyncpg.Connection, insert_chunk: Callable[..., Awaitable[int]]
) -> None:
    await insert_chunk(text="Stellen Sie das Gerät auf eine ebene Fläche.")

    results = await search_lexical(
        pg_conn, object_id=_TEST_OBJECT_ID, query="Kaffeemaschine explodiert", top_k=10
    )

    assert results == []


async def test_search_lexical_respects_top_k(
    pg_conn: asyncpg.Connection, insert_chunk: Callable[..., Awaitable[int]]
) -> None:
    for i in range(5):
        await insert_chunk(text=f"Reinigen Sie das Sieb Nummer {i}.")

    results = await search_lexical(
        pg_conn, object_id=_TEST_OBJECT_ID, query="Sieb reinigen", top_k=2
    )

    assert len(results) == 2


async def test_search_lexical_ignores_other_objects(
    pg_conn: asyncpg.Connection, insert_chunk: Callable[..., Awaitable[int]]
) -> None:
    await insert_chunk(
        text="Reinigen Sie die Siebe regelmäßig.",
        object_id="test-other-object",
    )

    results = await search_lexical(
        pg_conn, object_id=_TEST_OBJECT_ID, query="Sieb reinigen", top_k=10
    )

    assert results == []
