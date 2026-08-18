"""Layout-aware PDF chunking.

CRITICAL RULE (CLAUDE.md section 2): a chunk is one complete procedure step
or one complete procedure block — never split mid-step. This module reads
PyMuPDF's per-line font metadata to tell headings from body text and
numbered-step/bullet markers from continuation text, instead of splitting on
a fixed character count (see ADR-0007 for why).

The heuristics and thresholds below were calibrated against the real
Siemens SX63HX52BE manual (`objects/siemens-dishwasher`) by inspecting its
actual font sizes, weights and vector-drawing counts — not guessed. See each
constant's comment for what was actually observed. A differently laid-out
manual may need these re-tuned; that's an accepted M1 scope limit (this
project ingests object-specific manuals by design, not arbitrary PDFs).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

# ---------------------------------------------------------------- calibration
# Body text in the reference manual is 10.0pt. Real headings — both the
# ~14-15pt chapter/cover titles and a ~12pt bold sub-heading seen in the
# fault-code table ("Fehlercode / Fehleranzeige / Signal") — are >=12pt AND
# bold. A >=12pt *light*-weight lead sentence also exists
# ("Beachten Sie die nachfolgenden Sicherheitshinweise.") and is not a
# heading, hence the bold requirement, not size alone.
_HEADING_MIN_SIZE = 11.9
_HEADING_FONT_MARKER = "bol"  # matches "Bold" / "...-Bol" / "...-BolCon", case-insensitive
_HEADING_MAX_LEN = 100
_DOT_LEADER_RE = re.compile(r"\.{3,}")  # table-of-contents leader lines, e.g. "Sicherheit ..... 4"

# Spans reporting a near-zero size are invisible/duplicate text-layer
# artifacts: every chapter heading in the reference manual is duplicated as
# a same-text span at ~0pt right next to its real, visibly-sized rendering
# (confirmed by inspecting objects/siemens-dishwasher's actual PDF — e.g.
# "Störungen beheben" appears at both 0.0pt and 14.0pt on page 45). Drop
# them before any other processing so they don't contaminate body text.
_NOISE_MAX_SIZE = 1.0

# Running headers/footers sit in a fixed margin band regardless of font
# size (observed on a 595pt-tall page: header ~y=23-33, footer ~y=563-572).
# Filtering by page position rather than text pattern so it isn't fooled by
# a footer whose content (e.g. the page number) changes page to page.
_HEADER_FOOTER_MARGIN_PT = 40.0

_STEP_RE = re.compile(r"^(\d+)\.\s*(.+)$")
# ▶ marks a single-action instruction (e.g. "▶ Reinigen Sie die Siebe.").
# The second character is a Wingdings2 dingbat glyph that PyMuPDF decodes to
# U+00A1 (¡) — confirmed by inspecting its font in the reference manual —
# used for general informational bullet lists (e.g. safety notices), not
# procedural actions, but still one complete block each.
_BULLET_RE = re.compile(r"^[▶¡]\s*(.+)$")
# Allows a trailing footnote digit, e.g. "...Enthärtungsanlage.1"
_SENTENCE_END_RE = re.compile(r"[.!?]\d{0,2}\s*$")

# Pages with fewer vector-drawing paths than this are table borders/rules,
# not diagrams: in the reference manual, border/rule-only pages top out at
# 72 paths and real diagrams start at 90+, with a clear gap between the two
# — see the ADR / ingest run notes for the actual per-page distribution.
_DIAGRAM_MIN_VECTOR_PATHS = 80
_DIAGRAM_RENDER_DPI = 150


@dataclass
class Chunk:
    """One complete procedure step or block, ready to embed."""

    object_id: str
    manual_id: str
    page: int
    section: str
    step_no: int | None
    text: str
    figure_ids: list[str] = field(default_factory=list)


def chunk_manual(
    pdf_path: Path,
    *,
    object_id: str,
    manual_id: str,
    figures_dir: Path,
) -> list[Chunk]:
    """Chunk `pdf_path` into `Chunk`s and extract its figures.

    Figures are extracted two ways, because the reference manual's actual
    instructional diagrams are vector line-art, not embedded raster images
    — `page.get_images()` alone finds only 17 incidental raster images
    (icons/logos) across the whole 64-page manual and misses every real
    diagram:
    - genuinely embedded raster images, via `get_images`/`extract_image`.
    - a full-page render (`_DIAGRAM_RENDER_DPI`) for any page whose
      vector-drawing path count is above `_DIAGRAM_MIN_VECTOR_PATHS`. This
      renders the *whole* page rather than cropping just the diagram — an
      accepted M1 simplification; revisit with per-diagram cropping if the
      AR overlay later needs a tighter image.
    """
    doc = pymupdf.open(pdf_path)
    try:
        lines = _extract_lines(doc)
        chunks = _lines_to_chunks(lines, object_id=object_id, manual_id=manual_id)
        figures_by_page = _extract_figures(doc, manual_dir=figures_dir / object_id / manual_id)
    finally:
        doc.close()

    # The table of contents has no sentence-ending punctuation on its
    # dot-leader lines ("Sicherheit ....... 4"), so _lines_to_chunks can't
    # tell where one entry ends and the next begins and collapses the whole
    # page into one multi-thousand-character chunk — confirmed on the
    # reference manual's real "Inhaltsverzeichnis" page. It carries no
    # procedural content, so it's dropped rather than embedded as noise.
    chunks = [c for c in chunks if c.section != "Inhaltsverzeichnis"]

    for chunk in chunks:
        chunk.figure_ids = figures_by_page.get(chunk.page, [])
    return chunks


@dataclass
class _Line:
    page: int
    text: str
    is_heading: bool


def _extract_lines(doc: pymupdf.Document) -> list[_Line]:
    """Walk every page in order, filtering noise and header/footer bands.

    `sort=True` asks PyMuPDF for reading order (top-to-bottom, then
    left-to-right) instead of raw content-stream order. This matters
    concretely for the reference manual's fault-code table: without it,
    the "Störung" / "Ursache" / "Störungsbehebung" columns are each their
    own text block and come back column-by-column, interleaving one row's
    cause with a *different* row's remedy text.
    """
    lines: list[_Line] = []
    for page in doc:
        page_no = page.number + 1
        page_height = page.rect.height
        text_dict = page.get_text("dict", sort=True)
        for block in text_dict["blocks"]:
            for raw_line in block.get("lines", []):
                bbox = raw_line["bbox"]
                if bbox[1] < _HEADER_FOOTER_MARGIN_PT:
                    continue
                if bbox[3] > page_height - _HEADER_FOOTER_MARGIN_PT:
                    continue
                spans = [s for s in raw_line["spans"] if s["size"] >= _NOISE_MAX_SIZE and s["text"]]
                if not spans:
                    continue
                heading_text = _heading_text(spans)
                if heading_text is not None:
                    lines.append(_Line(page=page_no, text=heading_text, is_heading=True))
                    continue
                text = _normalize_whitespace("".join(s["text"] for s in spans))
                if text:
                    lines.append(_Line(page=page_no, text=text, is_heading=False))
    return lines


def _heading_text(spans: list[dict[str, Any]]) -> str | None:
    """Return the heading text if any span in this line qualifies, else None."""
    for span in spans:
        text = _normalize_whitespace(span["text"])
        if (
            span["size"] >= _HEADING_MIN_SIZE
            and _HEADING_FONT_MARKER in span["font"].lower()
            and 2 <= len(text) <= _HEADING_MAX_LEN
            and not _DOT_LEADER_RE.search(text)
            and not text.isdigit()
        ):
            return text
    return None


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _starts_new_block(current_text: str, next_line: str) -> bool:
    """True if `next_line` looks like a new block, not the same sentence wrapping.

    Requires *both* that the accumulated text already ends in terminal
    punctuation and that the next line starts with an uppercase letter —
    the first condition alone would misfire on an abbreviation like
    "z. B." (lowercase continuation after the period). A hyphenated
    line-wrap ("Heizele-") never ends in terminal punctuation, so
    hyphenated words still merge correctly across the line break without
    any hyphen-specific handling.
    """
    return bool(_SENTENCE_END_RE.search(current_text)) and next_line[:1].isupper()


def _lines_to_chunks(lines: list[_Line], *, object_id: str, manual_id: str) -> list[Chunk]:
    """Group lines into chunks, never splitting a numbered step or bullet.

    A chunk can span a page break: if a step's text is still open when a
    page ends and the next page doesn't start with a new heading/marker,
    the continuation is appended to the same chunk rather than starting a
    new one. `page` records where the chunk *begins*.

    An unmarked line only extends the currently open chunk if it looks like
    the same sentence wrapping onto a new line (the open chunk's text
    doesn't yet end in `.`/`!`/`?`); once a sentence has ended, the next
    unmarked line starts a fresh chunk instead of being glued onto it. This
    matters for e.g. the fault-code table's "Ursache" cells, which are
    unmarked text ("Zulaufschlauch ist geknickt.") immediately followed by
    a `▶`-marked remedy: without this check they'd merge into whatever
    chunk came before them instead of starting their own.
    Known limitation: that cause line and its remedy still end up as two
    adjacent chunks rather than one paired unit — reuniting them would need
    table-column-aware parsing, out of scope for a generic layout chunker.
    """
    chunks: list[Chunk] = []
    current: Chunk | None = None
    section = ""

    def flush() -> None:
        nonlocal current
        if current is not None:
            chunks.append(current)
            current = None

    for line in lines:
        if line.is_heading:
            flush()
            section = line.text
            continue

        step_match = _STEP_RE.match(line.text)
        bullet_match = _BULLET_RE.match(line.text)
        if step_match is not None:
            flush()
            current = Chunk(
                object_id=object_id,
                manual_id=manual_id,
                page=line.page,
                section=section,
                step_no=int(step_match.group(1)),
                text=step_match.group(2),
            )
        elif bullet_match is not None:
            flush()
            current = Chunk(
                object_id=object_id,
                manual_id=manual_id,
                page=line.page,
                section=section,
                step_no=None,
                text=bullet_match.group(1),
            )
        elif current is not None and not _starts_new_block(current.text, line.text):
            current.text = f"{current.text} {line.text}"
        elif current is not None:
            flush()
            current = Chunk(
                object_id=object_id,
                manual_id=manual_id,
                page=line.page,
                section=section,
                step_no=None,
                text=line.text,
            )
        else:
            current = Chunk(
                object_id=object_id,
                manual_id=manual_id,
                page=line.page,
                section=section,
                step_no=None,
                text=line.text,
            )

    flush()
    return chunks


def _extract_figures(doc: pymupdf.Document, *, manual_dir: Path) -> dict[int, list[str]]:
    """Extract figures per page, returning {page_number: [figure_id, ...]}."""
    manual_dir.mkdir(parents=True, exist_ok=True)
    figures_by_page: dict[int, list[str]] = {}

    for page in doc:
        page_no = page.number + 1
        figure_ids: list[str] = []

        for image in page.get_images(full=True):
            xref = image[0]
            extracted = doc.extract_image(xref)
            figure_id = f"p{page_no}_{xref}"
            path = manual_dir / f"{figure_id}.{extracted['ext']}"
            path.write_bytes(extracted["image"])
            figure_ids.append(figure_id)

        if len(page.get_drawings()) >= _DIAGRAM_MIN_VECTOR_PATHS:
            figure_id = f"p{page_no}_vector"
            path = manual_dir / f"{figure_id}.png"
            pix = page.get_pixmap(dpi=_DIAGRAM_RENDER_DPI)
            pix.save(path)
            figure_ids.append(figure_id)

        if figure_ids:
            figures_by_page[page_no] = figure_ids

    return figures_by_page
