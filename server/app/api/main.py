"""FastAPI application entrypoint.

Only the `/health` endpoint lives here for now; the orchestrator's WebSocket
handler is added in a later slice.
"""

import contextlib
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

import asyncpg
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.telemetry.logging import configure_logging, get_logger, new_trace_id

configure_logging()
logger = get_logger()


def _get_version() -> str:
    try:
        return version("arsa")
    except PackageNotFoundError:
        return "0.0.0-dev"


_VERSION = _get_version()

app = FastAPI(title="ARSA edge server", version=_VERSION)


@app.middleware("http")
async def bind_trace_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Bind a fresh trace_id to every request's log context."""
    trace_id = new_trace_id()
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


class ModelsInfo(BaseModel):
    vlm: str
    embed: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    object_id: str
    models: ModelsInfo
    db: Literal["ok", "down"]


async def _check_db(settings: Settings) -> Literal["ok", "down"]:
    """Attempt a short-lived connection to Postgres to confirm it is reachable."""
    try:
        conn = await asyncpg.connect(dsn=settings.database_dsn, timeout=2.0)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        return "down"
    with contextlib.suppress(OSError, asyncpg.PostgresError):
        await conn.close()
    return "ok"


@app.get("/health")
async def health() -> HealthResponse:
    settings = get_settings()
    db_status = await _check_db(settings)
    logger.info("health_check", db=db_status)
    return HealthResponse(
        status="ok",
        version=_VERSION,
        object_id=settings.arsa_object,
        models=ModelsInfo(vlm=settings.arsa_vlm_model, embed=settings.arsa_embed_model),
        db=db_status,
    )
