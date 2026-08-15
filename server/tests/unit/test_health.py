"""Unit tests for GET /health.

No network: asyncpg.connect is monkeypatched, so this never touches a real
Postgres instance (see CLAUDE.md section 7 — no network in unit tests).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


class _FakeConnection:
    async def close(self) -> None:
        return None


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_returns_200_with_expected_keys(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    async def fake_connect(*_args: Any, **_kwargs: Any) -> _FakeConnection:
        return _FakeConnection()

    monkeypatch.setattr("app.api.main.asyncpg.connect", fake_connect)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"status", "version", "object_id", "models", "db"}
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["models"].keys() == {"vlm", "embed"}


def test_health_reports_db_down_when_unreachable(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    async def fake_connect_fails(*_args: Any, **_kwargs: Any) -> _FakeConnection:
        raise OSError("connection refused")

    monkeypatch.setattr("app.api.main.asyncpg.connect", fake_connect_fails)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["db"] == "down"
