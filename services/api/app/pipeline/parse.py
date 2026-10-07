"""Turn uploaded files into page-numbered text."""

import io
from dataclasses import dataclass

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUPPORTED_MIME_TYPES = {PDF_MIME, DOCX_MIME}

# Below this many characters per page on average, a PDF is treated as scanned.
MIN_CHARS_PER_PAGE = 200


class UnsupportedDocument(ValueError):
    pass


@dataclass
class Page:
    number: int | None  # 1-based; None when the format has no pages (DOCX)
    text: str


@dataclass
class ParsedDocument:
    pages: list[Page]
    page_count: int | None
    text_source: str  # "text_layer" | "docx" | "needs_ocr"

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.pages)


def sniff_mime_type(data: bytes, filename: str) -> str:
    """Identify the file by content, not by the client-provided type."""
    if data.startswith(b"%PDF-"):
        return PDF_MIME
    if data.startswith(b"PK") and filename.lower().endswith(".docx"):
        return DOCX_MIME
    raise UnsupportedDocument("Only PDF and Word (.docx) files are supported")


def parse_pdf(data: bytes) -> ParsedDocument:
    import pdfplumber

    pages: list[Page] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
            pages.append(Page(i, text))
    page_count = len(pages)
    chars = sum(len(p.text.strip()) for p in pages)
    scanned = page_count > 0 and chars / page_count < MIN_CHARS_PER_PAGE
    return ParsedDocument(pages, page_count, "needs_ocr" if scanned else "text_layer")


def parse_docx(data: bytes) -> ParsedDocument:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text.strip() for cell in row.cells))
    return ParsedDocument([Page(None, "\n".join(lines))], None, "docx")


def parse(data: bytes, mime_type: str) -> ParsedDocument:
    if mime_type == PDF_MIME:
        return parse_pdf(data)
    if mime_type == DOCX_MIME:
        return parse_docx(data)
    raise UnsupportedDocument(f"Unsupported file type: {mime_type}")
