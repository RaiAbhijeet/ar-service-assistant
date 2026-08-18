"""CLI entrypoint: `python -m ingest.run --object <id>` (see Makefile's `ingest` target).

For each manual listed in the object's `object.yaml`: download -> verify
hash -> chunk -> embed -> store. Applies `schema.sql` idempotently first.
Re-running for the same object replaces its rows (see ingest.embed.store_chunks).
"""

import argparse
import asyncio
from pathlib import Path

import asyncpg
from pgvector.asyncpg import register_vector

from app.config import get_settings
from app.telemetry.logging import configure_logging, get_logger
from ingest.chunk import chunk_manual
from ingest.download import download_manual
from ingest.embed import embed_chunks, store_chunks
from ingest.manifest import load_manifest

logger = get_logger()

# Repo-layout conventions (CLAUDE.md section 3), not per-deployment config —
# these paths are the same in every environment this runs in.
_OBJECTS_DIR = Path("objects")
_MANUALS_DIR = Path("data/manuals")
_FIGURES_DIR = Path("data/manuals/figures")
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def run(object_id: str) -> None:
    settings = get_settings()
    manifest = load_manifest(_OBJECTS_DIR, object_id)

    conn = await asyncpg.connect(dsn=settings.database_dsn)
    try:
        await conn.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))
        await register_vector(conn)

        for manual in manifest.manuals:
            pdf_path = download_manual(manual, _MANUALS_DIR / object_id)
            chunks = chunk_manual(
                pdf_path,
                object_id=object_id,
                manual_id=manual.id,
                figures_dir=_FIGURES_DIR,
            )
            logger.info("ingest.chunked", manual_id=manual.id, count=len(chunks))

            vectors = await embed_chunks(
                chunks,
                ollama_host=settings.ollama_host,
                model=settings.arsa_embed_model,
            )
            await store_chunks(chunks, vectors, object_id=object_id, conn=conn)
    finally:
        await conn.close()

    logger.info("ingest.done", object_id=object_id, manuals=len(manifest.manuals))


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Download, chunk and embed an object's manuals.")
    parser.add_argument("--object", required=True, help="Object id (a folder name under objects/).")
    args = parser.parse_args()
    asyncio.run(run(args.object))


if __name__ == "__main__":
    main()
