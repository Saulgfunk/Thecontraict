import pytest

from app.pipeline.parse import (
    DOCX_MIME,
    PDF_MIME,
    Page,
    UnsupportedDocument,
    parse,
    sniff_mime_type,
)
from app.pipeline.segment import match_heading, segment
from tests.samples import blank_pdf, msa_docx, msa_pdf


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("1. DEFINITIONS", ("1", "DEFINITIONS")),
        ("12.3 Notices", ("12.3", "Notices")),
        ("2.1 This Agreement commences on 1 January 2025.", ("2.1", None)),
        ("7 TERM AND TERMINATION", ("7", "TERM AND TERMINATION")),
        ("Clause 5: Payment", ("Clause 5", "Payment")),
        ("SECTION 2.1 - Fees", ("Section 2.1", "Fees")),
        ("Schedule 1 Services", ("Schedule 1", "Services")),
        ("Annex A", ("Annex A", None)),
        ("30. days after the invoice date", None),
        ("90 days' written notice", None),
        ("The parties agree as follows.", None),
        ("", None),
    ],
)
def test_match_heading(line: str, expected: tuple[str, str | None] | None) -> None:
    assert match_heading(line) == expected


def test_segment_numbered_contract_with_pages() -> None:
    pages = [
        Page(1, "MASTER AGREEMENT\nBetween A and B.\n1. TERM\n1.1 Starts on 1 May 2025."),
        Page(2, "continues for 12 months.\n2. FEES\nFees are EUR 10."),
    ]
    clauses = segment(pages)
    assert [(c.number, c.heading) for c in clauses] == [
        (None, "Preamble"),
        ("1", "TERM"),
        ("1.1", None),
        ("2", "FEES"),
    ]
    clause_1_1 = clauses[2]
    assert "continues for 12 months." in clause_1_1.text
    assert (clause_1_1.page_start, clause_1_1.page_end) == (1, 2)


def test_segment_without_headings_falls_back_to_chunks() -> None:
    text = "\n".join(f"Paragraph {i} " + "word " * 60 for i in range(20))
    clauses = segment([Page(1, text)])
    assert len(clauses) > 1
    assert all(c.number is None and c.page_start == 1 for c in clauses)
    assert all(len(c.text) <= 1600 for c in clauses)


def test_parse_docx_and_pdf() -> None:
    docx_bytes = msa_docx()
    assert sniff_mime_type(docx_bytes, "msa.docx") == DOCX_MIME
    parsed = parse(docx_bytes, DOCX_MIME)
    assert parsed.text_source == "docx"
    assert "renews automatically" in parsed.text

    pdf_bytes = msa_pdf()
    assert sniff_mime_type(pdf_bytes, "msa.pdf") == PDF_MIME
    parsed = parse(pdf_bytes, PDF_MIME)
    assert parsed.page_count == 2
    assert parsed.text_source == "text_layer"
    assert "2. TERM" in parsed.pages[0].text


def test_scanned_pdf_detected() -> None:
    parsed = parse(blank_pdf(), PDF_MIME)
    assert parsed.text_source == "needs_ocr"


def test_unsupported_files_rejected() -> None:
    with pytest.raises(UnsupportedDocument):
        sniff_mime_type(b"hello", "notes.txt")
    with pytest.raises(UnsupportedDocument):
        sniff_mime_type(b"PK\x03\x04...", "archive.zip")
