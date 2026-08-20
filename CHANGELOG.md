# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) ·
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]
### Added
- Repository skeleton, CLAUDE.md, ADR templates, CI scaffolding
- **M0 complete** — server skeleton (FastAPI `/health`, Postgres+pgvector,
  Docker Compose), Unity 6 client skeleton (OpenXR, URP, ARSA.* assemblies,
  Meta Passthrough Building Block, confirmed working on-device), and CI
  (GitHub Actions for both, pre-commit, Dependabot). See `docs/logbook/M0.md`.
- Demo object switched from `bike-drivetrain` to `siemens-dishwasher`
  (SX63HX52BE); the old placeholder object folder is removed.
- **M1.1 — manual ingestion** (`server/ingest/`): download + SHA-256
  verification, layout-aware PDF chunking (PyMuPDF, see
  [ADR-0007](docs/adr/0007-pymupdf-for-layout-aware-chunking.md)), figure
  extraction, and embedding into Postgres+pgvector via Ollama/bge-m3.
- **M1.2 — hybrid retrieval** (`server/app/retrieval/`): dense (pgvector
  cosine) + lexical (Postgres German full-text) search, fused with
  Reciprocal Rank Fusion. Refusing to answer below `min_retrieval_score`
  is a deliberate, tested behaviour (ADR-0006).
- **M1.3 — evaluation harness** (`server/eval/`): validates and runs the
  hand-written 60-entry `golden_de.yaml` golden set against real
  retrieval, gated in CI on `recall_at_5` and `refusal_accuracy`
  (`server/eval/thresholds.yaml`). First real measured run:
  `recall_at_5 = 0.732` (target ≥0.85) and `refusal_accuracy = 0.0`
  (target ≥0.95) — both below target; root-caused rather than papered
  over, see [ADR-0008](docs/adr/0008-known-m1-recall-gap.md).
