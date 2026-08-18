# ADR-0007 — PyMuPDF for layout-aware chunking

- **Status:** accepted
- **Date:** 2026-08-18
- **Deciders:** RaiAbhijeet

## Context

CLAUDE.md section 2 requires that a chunk is one complete procedure step or
block — never split mid-step — because a partial step retrieved and shown
alone (e.g. "1. Ziehen Sie den Netzstecker" without the step that follows
it) would be actively unsafe, not just unhelpful. It also requires every
instruction to be traceable to a retrieved chunk with a page number shown in
the UI, and (via ADR-0006) that facts never be fabricated.

A chunker that only sees flat extracted text can't reliably tell a section
heading from body text, or find step boundaries beyond a regex on the
visible characters — and it can't recover the figures a step references
(e.g. the Siemens manual's `→ "Abwasserpumpe reinigen", Seite 59`
cross-references, and inline diagrams) at all.

## Decision

We will use PyMuPDF (`pymupdf` on PyPI, imported as `fitz`) in
`server/ingest/chunk.py` for both text+layout extraction
(`page.get_text("dict")`, which gives per-line font size and position — used
to tell headings from body text) and figure extraction
(`page.get_images()` / `page.extract_image()`), in the same pass over each
page.

## Consequences

**Positive**
- Chunk boundaries follow the manual's actual structure (headings, numbered
  steps, `▶` single-action bullets) instead of an arbitrary character count
  — this is what makes the "never split mid-step" rule enforceable at all.
- Figures are extracted at the same page granularity as the text referencing
  them, so `figure_ids` can be attached without a second parsing pass.
- Pure-Python wheel — no external binary dependency (e.g. poppler), which
  keeps the Docker build simple.

**Negative / accepted costs**
- The heading/step-boundary heuristics (font-size threshold, step-marker
  regexes) are tuned against this project's manuals, not generic; a very
  differently laid-out manual may need heuristic changes. Accepted as an M1
  scope limit — this project ingests object-specific manuals by design, not
  arbitrary PDFs.
- PyMuPDF is AGPL-3.0 for the open-source distribution used here. This
  project doesn't redistribute it or offer it as a hosted service to third
  parties — it runs offline, at ingest time, in a portfolio/demo repo — so
  this is acceptable as-is. Re-check before any commercial use.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| `pypdf` / `pdfplumber` text-only extraction + regex splitter | No font-size/layout metadata, so heading-vs-body detection is unreliable; no built-in image extraction. |
| Fixed-length text splitter (e.g. LangChain's `RecursiveCharacterTextSplitter`) | Splits by character count, blind to step boundaries — directly violates the "never split mid-step" rule. LangChain itself is also excluded by CLAUDE.md section 2. |
| `pdftotext` (poppler) via subprocess | Loses per-line font-size metadata needed for heading detection; adds a native binary dependency to the Docker image instead of a pure-Python wheel. |

## References

- CLAUDE.md section 2 (safety behaviour: never fabricate step order)
- ADR-0006 (refusal-over-generation)
- `objects/siemens-dishwasher/object.yaml`'s fault-code table — the real
  numbered-step content this chunker must not split.
