"""Shared fixtures for tests needing a real Postgres+pgvector instance.

Per CLAUDE.md section 7 ("no network in unit tests"), no live Ollama call
happens anywhere in these fixtures — only a genuinely *local* Postgres,
which the project's own CI already provisions for exactly this purpose
(see server.yml's `postgres` service and its comment anticipating "a real
integration test [that] needs the live postgres service"). Tests using
`pg_conn` skip gracefully if that Postgres isn't reachable, so `pytest`
still passes for anyone running it without the edge stack up.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

from app.config import get_settings

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "ingest" / "schema.sql"

# Dedicated object ids for these fixtures — both prefixed "test-" so the
# cleanup below can catch every fixture row (including ones tests insert
# under a *different* object id on purpose, e.g. to prove object_id
# filtering works) without ever touching real ingested data (e.g. the
# actual siemens-dishwasher rows) sitting in the same table.
TEST_OBJECT_ID = "test-retrieval-fixture"
_CLEANUP_PATTERN = "test-%"


@pytest_asyncio.fixture
async def pg_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """A real connection to the local test Postgres, schema applied.

    Skips the test (doesn't fail it) if Postgres isn't reachable — this is
    real local infrastructure, not something every unit test run needs.
    """
    dsn = get_settings().database_dsn
    try:
        conn = await asyncpg.connect(dsn=dsn, timeout=2.0)
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        pytest.skip(f"Postgres not reachable at {dsn}: {exc}")
    await conn.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))
    await conn.execute("DELETE FROM chunks WHERE object_id LIKE $1", _CLEANUP_PATTERN)
    try:
        yield conn
    finally:
        await conn.execute("DELETE FROM chunks WHERE object_id LIKE $1", _CLEANUP_PATTERN)
        await conn.close()


@pytest_asyncio.fixture
def insert_chunk(
    pg_conn: asyncpg.Connection,
) -> Callable[..., Awaitable[int]]:
    """Return an async callable that inserts one row into `chunks`, returning its id."""

    async def _insert(
        *,
        text: str,
        page: int = 1,
        section: str = "Test",
        step_no: int | None = None,
        embedding: list[float] | None = None,
        object_id: str = TEST_OBJECT_ID,
    ) -> int:
        if embedding is not None:
            from app.retrieval.dense import vector_literal

            row = await pg_conn.fetchrow(
                """
                INSERT INTO chunks (object_id, manual_id, page, section, step_no, text, embedding)
                VALUES ($1, 'test-manual', $2, $3, $4, $5, $6::vector)
                RETURNING id
                """,
                object_id,
                page,
                section,
                step_no,
                text,
                vector_literal(embedding),
            )
        else:
            row = await pg_conn.fetchrow(
                """
                INSERT INTO chunks (object_id, manual_id, page, section, step_no, text)
                VALUES ($1, 'test-manual', $2, $3, $4, $5)
                RETURNING id
                """,
                object_id,
                page,
                section,
                step_no,
                text,
            )
        id_: int = row["id"]
        return id_

    return _insert
