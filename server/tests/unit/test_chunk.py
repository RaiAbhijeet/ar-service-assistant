"""Unit tests for ingest.chunk.

Builds tiny synthetic PDFs in-memory with PyMuPDF itself (no binary fixture
committed to the repo) so these tests don't depend on any real manual.
Heuristic thresholds mirror the real values calibrated against the actual
Siemens manual in chunk.py — see that module's docstring for where they
came from.
"""

from pathlib import Path

import pymupdf

from ingest.chunk import chunk_manual

_BULLET_CHAR = chr(0xA1)  # "¡" — one of the two real bullet glyphs chunk.py recognizes


def _build_pdf(tmp_path: Path, pages: list[list[tuple[str, float, str]]]) -> Path:
    """Build a PDF from `pages`: each page is a list of (text, fontsize, fontname).

    Lines are placed top-to-bottom with generous spacing and margins well
    inside chunk.py's header/footer exclusion band.
    """
    doc = pymupdf.open()
    for page_lines in pages:
        page = doc.new_page()
        y = 100.0
        for text, size, fontname in page_lines:
            page.insert_text((72, y), text, fontsize=size, fontname=fontname)
            y += 20.0
    path = tmp_path / "test.pdf"
    doc.save(path)
    doc.close()
    return path


def _chunk(tmp_path: Path, pages: list[list[tuple[str, float, str]]]) -> list:
    pdf_path = _build_pdf(tmp_path, pages)
    return chunk_manual(
        pdf_path,
        object_id="test-object",
        manual_id="test-manual",
        figures_dir=tmp_path / "figures",
    )


def test_numbered_step_wrapped_across_two_lines_is_one_chunk(tmp_path: Path) -> None:
    """The CRITICAL RULE this module exists for: a step is never split."""
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Anleitung", 14.0, "hebo"),
                ("1. Ziehen Sie den Netzstecker und warten Sie, bis das Gerät", 10.0, "helv"),
                ("vollständig abgekühlt ist.", 10.0, "helv"),
            ]
        ],
    )

    assert len(chunks) == 1
    assert chunks[0].step_no == 1
    assert chunks[0].text == (
        "Ziehen Sie den Netzstecker und warten Sie, bis das Gerät vollständig abgekühlt ist."
    )


def test_two_numbered_steps_stay_separate_chunks(tmp_path: Path) -> None:
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Anleitung", 14.0, "hebo"),
                ("1. Schalten Sie das Gerät aus.", 10.0, "helv"),
                ("2. Ziehen Sie den Netzstecker.", 10.0, "helv"),
            ]
        ],
    )

    assert len(chunks) == 2
    assert [c.step_no for c in chunks] == [1, 2]
    assert chunks[0].text == "Schalten Sie das Gerät aus."
    assert chunks[1].text == "Ziehen Sie den Netzstecker."


def test_bullet_marker_starts_a_new_chunk(tmp_path: Path) -> None:
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Anleitung", 14.0, "hebo"),
                (f"{_BULLET_CHAR} Reinigen Sie die Siebe.", 10.0, "helv"),
                (f"{_BULLET_CHAR} Prüfen Sie die Dichtung.", 10.0, "helv"),
            ]
        ],
    )

    assert len(chunks) == 2
    assert all(c.step_no is None for c in chunks)
    assert chunks[0].text == "Reinigen Sie die Siebe."
    assert chunks[1].text == "Prüfen Sie die Dichtung."


def test_heading_sets_section_and_is_not_its_own_chunk(tmp_path: Path) -> None:
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Reinigen und Pflegen", 14.0, "hebo"),
                ("1. Entnehmen Sie das Sieb.", 10.0, "helv"),
            ]
        ],
    )

    assert len(chunks) == 1
    assert chunks[0].section == "Reinigen und Pflegen"
    assert "Reinigen und Pflegen" not in chunks[0].text


def test_unmarked_paragraph_after_a_finished_sentence_starts_a_new_chunk(
    tmp_path: Path,
) -> None:
    """Two unmarked lines that don't wrap the same sentence must not merge.

    This is the fault-code-table regression: an unmarked "Ursache" line
    must not get glued onto whatever chunk preceded it.
    """
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Störungen beheben", 14.0, "hebo"),
                ("1. Schließen Sie den Wasserhahn.", 10.0, "helv"),
                ("Zulaufschlauch ist geknickt.", 10.0, "helv"),
            ]
        ],
    )

    assert len(chunks) == 2
    assert chunks[0].step_no == 1
    assert chunks[0].text == "Schließen Sie den Wasserhahn."
    assert chunks[1].step_no is None
    assert chunks[1].text == "Zulaufschlauch ist geknickt."


def test_unmarked_paragraph_wraps_mid_sentence_within_one_chunk(tmp_path: Path) -> None:
    """A plain (unmarked) paragraph that wraps *mid-sentence* stays one chunk."""
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Sicherheit", 14.0, "hebo"),
                (
                    "Kleinere Störungen an Ihrem Gerät können Sie selbst beheben, wenn Sie",
                    10.0,
                    "helv",
                ),
                ("die Hinweise in diesem Kapitel befolgen.", 10.0, "helv"),
            ]
        ],
    )

    assert len(chunks) == 1
    assert chunks[0].step_no is None
    assert chunks[0].text == (
        "Kleinere Störungen an Ihrem Gerät können Sie selbst beheben, wenn Sie "
        "die Hinweise in diesem Kapitel befolgen."
    )


def test_two_unmarked_complete_sentences_split_into_separate_chunks(tmp_path: Path) -> None:
    """Known tradeoff (documented in chunk.py): once an unmarked line ends in
    terminal punctuation, the next unmarked line starts a new chunk even if
    it's really the same paragraph's next sentence — accepted because the
    alternative (always merge) is what caused the fault-code-table bug this
    module was built to avoid (see the regression test above)."""
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Sicherheit", 14.0, "hebo"),
                ("Kleinere Störungen an Ihrem Gerät können Sie selbst beheben.", 10.0, "helv"),
                ("Nutzen Sie dazu die Informationen in diesem Kapitel.", 10.0, "helv"),
            ]
        ],
    )

    assert len(chunks) == 2
    assert [c.step_no for c in chunks] == [None, None]


def test_step_continues_across_a_page_break_into_one_chunk(tmp_path: Path) -> None:
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Anleitung", 14.0, "hebo"),
                ("1. Schrauben Sie den Wasseranschluss ab, drehen Sie ihn", 10.0, "helv"),
            ],
            [
                ("vorsichtig gegen den Uhrzeigersinn.", 10.0, "helv"),
            ],
        ],
    )

    assert len(chunks) == 1
    assert chunks[0].page == 1  # records the page the step *begins* on
    assert chunks[0].step_no == 1
    assert chunks[0].text == (
        "Schrauben Sie den Wasseranschluss ab, drehen Sie ihn vorsichtig gegen den Uhrzeigersinn."
    )


def test_heading_on_next_page_closes_the_previous_chunk(tmp_path: Path) -> None:
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Anleitung", 14.0, "hebo"),
                ("1. Erster Schritt.", 10.0, "helv"),
            ],
            [
                ("Reinigen und Pflegen", 14.0, "hebo"),
                ("1. Zweiter Schritt.", 10.0, "helv"),
            ],
        ],
    )

    assert len(chunks) == 2
    assert chunks[0].page == 1
    assert chunks[0].section == "Anleitung"
    assert chunks[1].page == 2
    assert chunks[1].section == "Reinigen und Pflegen"


def test_table_of_contents_section_is_dropped(tmp_path: Path) -> None:
    chunks = _chunk(
        tmp_path,
        [
            [
                ("Inhaltsverzeichnis", 14.0, "hebo"),
                ("Sicherheit ..................... 4", 10.0, "helv"),
                ("Reinigen und Pflegen ......... 41", 10.0, "helv"),
            ]
        ],
    )

    assert chunks == []
