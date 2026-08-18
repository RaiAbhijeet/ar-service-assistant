"""Hybrid retrieval: dense (pgvector cosine) + lexical (Postgres FTS), fused with RRF.

See ADR-0003 (RAG instead of fine-tuning) and ADR-0006 (refusal over
generation) — an empty result from `RetrievalService.search` is a valid,
expected outcome, not an error.
"""
