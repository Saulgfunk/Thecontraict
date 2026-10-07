"""AI drafting of formal notices (non-renewal, termination, renegotiation, option exercise).

The model gets the full contract (clauses as a cited document) plus facts the system has
calculated (current term, the deadline and how it was derived, the notice clause details),
and writes a letter for a lawyer to review. It never sends anything.
"""

import enum
import io
from datetime import date
from typing import Any

from app.chat import SourceDoc
from app.models import Contract, Deadline

DRAFTING_SYSTEM_PROMPT = """\
You draft formal contractual notices for a legal team. Write in clear, formal English \
suitable for sending on the sender's letterhead.

- Base every statement on the contract provided. Refer to clauses by their numbers as \
printed in the contract (for example "clause 2.2"), not by internal references like C5.
- Comply with the contract's notice requirements: address the notice to the party and \
address the contract specifies, and state the method of delivery it requires.
- Identify the agreement precisely (title, parties, date) and state the effect of the \
notice and its effective date.
- Use [square brackets] for anything you cannot determine from the contract, such as a \
signatory's name or a missing address. Never invent facts.
- Output only the letter: no preamble, no commentary, no markdown formatting.
"""


class NoticeKind(enum.StrEnum):
    NON_RENEWAL = "non_renewal"
    TERMINATION = "termination"
    RENEGOTIATION = "renegotiation"
    OPTION_EXERCISE = "option_exercise"


KIND_INSTRUCTIONS = {
    NoticeKind.NON_RENEWAL: (
        "Draft a notice of non-renewal: the sender does not wish the agreement to renew at "
        "the end of the current term, so it will expire at the end of that term."
    ),
    NoticeKind.TERMINATION: (
        "Draft a notice of termination under the contract's termination provisions. State "
        "the clause relied on and the date termination takes effect."
    ),
    NoticeKind.RENEGOTIATION: (
        "Draft a letter that preserves the sender's position (giving notice of non-renewal "
        "where the contract requires it to stop automatic renewal) while inviting the other "
        "party to negotiate revised terms before the current term ends."
    ),
    NoticeKind.OPTION_EXERCISE: (
        "Draft a notice exercising the option described in the contract (for example an "
        "option to extend or renew), within the window the contract allows."
    ),
}


def build_request(
    contract: Contract,
    clauses: SourceDoc | None,
    kind: NoticeKind,
    deadline: Deadline | None,
    sender: str | None,
    instructions: str | None,
    today: date,
) -> list[dict[str, Any]]:
    facts = [
        f"Today's date: {today:%d %B %Y}.",
        f"Agreement: {contract.title}.",
    ]
    parties = ", ".join(f"{p.get('name')} ({p.get('role')})" for p in contract.parties or [])
    if parties:
        facts.append(f"Parties: {parties}.")
    if contract.counterparty_name:
        facts.append(f"The notice is addressed to the counterparty: {contract.counterparty_name}.")
    if sender:
        facts.append(f"The sender (our side) is: {sender}.")
    if contract.notice_details:
        facts.append(f"Notice requirements found in the contract: {contract.notice_details}.")
    if deadline:
        facts.append(
            f"The relevant deadline is '{deadline.label}' on {deadline.due_date:%d %B %Y}, "
            "calculated as follows: " + " / ".join(deadline.derivation)
        )
    content: list[dict[str, Any]] = []
    if clauses:
        content.append(clauses.to_param())
    text = (
        KIND_INSTRUCTIONS[kind]
        + "\n\nFacts calculated by the system (check them against the contract):\n- "
        + "\n- ".join(facts)
    )
    if instructions:
        text += f"\n\nAdditional instructions from the user:\n{instructions}"
    content.append({"type": "text", "text": text})
    return [{"role": "user", "content": content}]


def render_docx(title: str, text: str) -> bytes:
    import docx
    from docx.shared import Pt

    document = docx.Document()
    style = document.styles["Normal"]
    style.font.name = "Calibri"  # type: ignore[attr-defined]
    style.font.size = Pt(11)  # type: ignore[attr-defined]
    document.core_properties.title = title
    for block in text.replace("\r\n", "\n").split("\n\n"):
        paragraph = document.add_paragraph()
        lines = block.split("\n")
        for i, line in enumerate(lines):
            run = paragraph.add_run(line)
            if i < len(lines) - 1:
                run.add_break()
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
