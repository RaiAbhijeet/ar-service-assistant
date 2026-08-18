"""Manual ingestion pipeline: download -> chunk -> embed.

Per CLAUDE.md section 2, this is the only package in the codebase allowed to
make outbound internet requests, and only when run explicitly via
`python -m ingest.run` (see `Makefile`'s `ingest` target) — never at request
time from `app/`.
"""
