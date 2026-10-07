"""Split document text into clauses: the units the AI cites and users click through to.

Headings we recognise (one per line):
- numbered clauses: "1.", "1.2", "12.3.4 Notices", "7. TERM AND TERMINATION"
- an un-dotted number followed by an upper-case heading: "1 DEFINITIONS"
- "Clause 5", "Section 2.1", "Article 3"
- "Schedule 1", "Annex A", "Appendix 2", "Exhibit B"

Text before the first heading becomes a "Preamble" clause. Documents without any
recognisable headings are split into paragraph chunks instead.
"""

import re
from dataclasses import dataclass

from app.pipeline.parse import Page

MAX_CLAUSE_CHARS = 6000
CHUNK_CHARS = 1500

_NUMBERED = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){1,4}|\d{1,3}\.)\s*(\S.*)?$")
_NUMBER_CAPS = re.compile(r"^(\d{1,3})\s+([A-Z][A-Z0-9 ,&'/\-]{2,80})$")
_KEYWORD = re.compile(
    r"^(clause|section|article)\s+(\d{1,3}(?:\.\d{1,3})*[a-z]?)\b[\s:.\-–]*(.*)$", re.IGNORECASE
)
_ANNEX = re.compile(
    r"^(schedule|annex|appendix|exhibit)\s+([0-9]{1,3}|[A-Z]|[IVX]{1,5})\b[\s:.\-–]*(.*)$",
    re.IGNORECASE,
)


@dataclass
class ClauseDraft:
    number: str | None
    heading: str | None
    text: str
    page_start: int | None
    page_end: int | None


def _heading_text(rest: str | None) -> str | None:
    """Treat the remainder of a heading line as a title only if it looks like one."""
    if not rest:
        return None
    rest = rest.strip()
    if len(rest) <= 100 and not rest.endswith((".", ";", ",", ":")):
        return rest
    return None


def match_heading(line: str) -> tuple[str, str | None] | None:
    """Return (number, heading) if the line starts a clause."""
    line = line.strip()
    if not line or len(line) > 300:
        return None
    if m := _KEYWORD.match(line):
        return f"{m.group(1).title()} {m.group(2)}", _heading_text(m.group(3))
    if m := _ANNEX.match(line):
        return f"{m.group(1).title()} {m.group(2)}", _heading_text(m.group(3))
    if m := _NUMBERED.match(line):
        number = m.group(1).rstrip(".")
        rest = m.group(2)
        # Guard against wrapped sentences such as "30. days after..." starting a line.
        if rest and rest[0].islower():
            return None
        return number, _heading_text(rest)
    if m := _NUMBER_CAPS.match(line):
        return m.group(1), m.group(2).strip()
    return None


def _split_long(draft: ClauseDraft) -> list[ClauseDraft]:
    if len(draft.text) <= MAX_CLAUSE_CHARS:
        return [draft]
    parts: list[str] = []
    buf = ""
    for para in draft.text.split("\n"):
        if buf and len(buf) + len(para) > MAX_CLAUSE_CHARS:
            parts.append(buf)
            buf = ""
        buf = f"{buf}\n{para}" if buf else para
    if buf:
        parts.append(buf)
    title = draft.heading or draft.number or "Section"
    return [
        ClauseDraft(draft.number, f"{title} (part {i})", text, draft.page_start, draft.page_end)
        for i, text in enumerate(parts, start=1)
    ]


def _chunk(pages: list[Page]) -> list[ClauseDraft]:
    drafts: list[ClauseDraft] = []
    for page in pages:
        buf = ""
        for para in re.split(r"\n\s*\n|\n", page.text):
            para = para.strip()
            if not para:
                continue
            if buf and len(buf) + len(para) > CHUNK_CHARS:
                drafts.append(ClauseDraft(None, None, buf, page.number, page.number))
                buf = ""
            buf = f"{buf}\n{para}" if buf else para
        if buf:
            drafts.append(ClauseDraft(None, None, buf, page.number, page.number))
    return drafts


def segment(pages: list[Page]) -> list[ClauseDraft]:
    drafts: list[ClauseDraft] = []
    current: ClauseDraft | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal current, lines
        text = "\n".join(lines).strip()
        if current is not None and (text or current.heading):
            current.text = text
            drafts.append(current)
        lines = []

    headings_found = 0
    for page in pages:
        for raw in page.text.splitlines():
            heading = match_heading(raw)
            if heading:
                headings_found += 1
                flush()
                number, title = heading
                current = ClauseDraft(number, title, "", page.number, page.number)
                if title is None:
                    lines.append(raw.strip())
                continue
            if current is None:
                current = ClauseDraft(None, "Preamble", "", page.number, page.number)
            current.page_end = page.number
            lines.append(raw.rstrip())
    flush()

    if headings_found < 2:
        drafts = _chunk(pages)
    result: list[ClauseDraft] = []
    for d in drafts:
        result.extend(_split_long(d))
    return [d for d in result if d.text.strip() or d.heading]
