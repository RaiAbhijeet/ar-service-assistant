# Multi-stage build. Build context is server/ (see docker-compose.yml).

# ---------------------------------------------------------------------- builder
FROM python:3.12-slim AS builder

# Build tools for any dependency that needs to compile a C extension
# (e.g. asyncpg has manylinux wheels for this platform, but keep this in
# case a future dependency doesn't).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
COPY app ./app
# Dev deps (pytest, ruff, mypy, ...) are included here because `make test`,
# `make ingest` and `make eval` all run *inside* this image via
# `docker compose run --rm api ...` (see Makefile). There is no separate
# slimmed-down production image at this stage of the project.
RUN pip install --no-cache-dir ".[dev]"

# ---------------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

RUN groupadd --system arsa && useradd --system --gid arsa --home /app arsa

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
# WORKDIR creates /app as root; hand it to arsa so pytest/mypy/ruff caches
# (.pytest_cache, .mypy_cache, .ruff_cache) can be written when `make test`
# / `make lint`-equivalent commands run inside the container as the
# non-root user.
RUN chown arsa:arsa /app

COPY --chown=arsa:arsa app ./app
COPY --chown=arsa:arsa ingest ./ingest
COPY --chown=arsa:arsa tests ./tests
COPY --chown=arsa:arsa pyproject.toml ./

USER arsa
EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
