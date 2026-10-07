"""AI chat over contracts with clause-level citations.

Each contract is sent to Claude as a custom-content document whose content blocks are
its clauses, with citations enabled. Claude's citations come back as block ranges
(``content_block_location``), which map straight back to clause refs, so every cited
sentence links to the clause it relies on.

A workspace's contracts are all included when they fit comfortably in the context;
for larger workspaces, the most relevant clauses are selected with PostgreSQL full-text
search. A portfolio overview (titles, parties, dates, upcoming deadlines) is always
included so questions like "what expires next quarter" work too.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ChatMessage,
    Clause,
    Contract,
    Deadline,
    DeadlineStatus,
    Document,
    DocumentStatus,
)

MAX_FULL_TEXT_CHARS = 400_000  # roughly 100k tokens of contract text
MAX_SEARCH_CLAUSES = 60
HISTORY_MESSAGES = 12

SYSTEM_PROMPT = """\
You are a contract assistant for a legal team. Answer questions using only the \
contract documents provided in the conversation.

- Cite the clauses you rely on. Be precise about dates, periods, amounts and \
conditions, and quote the contract's wording where it matters.
- If the documents don't answer the question, say so plainly and say what is missing. \
Never fill gaps with assumptions or general knowledge presented as contract terms.
- The portfolio overview lists dates the system calculated from the contracts; say \
when an answer depends on such a calculated date or on terms marked as unconfirmed.
- Be concise: lead with the answer, then the supporting detail. Use short lists for \
multiple contracts.
- You provide information about the documents, not legal advice. Flag anything that \
looks ambiguous or that a lawyer should check.
"""


@dataclass
class SourceDoc:
    """A document sent to the model; ``refs[i]`` is the clause ref of content block i."""

    contract_id: uuid.UUID | None
    title: str
    context: str | None
    blocks: list[str]
    refs: list[str | None]
    block_contract_ids: list[uuid.UUID | None] = field(default_factory=list)

    def to_param(self) -> dict[str, Any]:
        param: dict[str, Any] = {
            "type": "document",
            "source": {
                "type": "content",
                "content": [{"type": "text", "text": b} for b in self.blocks],
            },
            "title": self.title[:500],
            "citations": {"enabled": True},
        }
        if self.context:
            param["context"] = self.context
        return param


def _period(amount: int | None, unit: str | None) -> str | None:
    return f"{amount} {unit}" if amount and unit else None


def _facts(contract: Contract, deadlines: list[Deadline]) -> str:
    parts = [
        f"Counterparty: {contract.counterparty_name}" if contract.counterparty_name else None,
        f"Type: {contract.contract_type}" if contract.contract_type else None,
        f"Status: {contract.status.replace('_', ' ')}",
        f"Effective: {contract.effective_date}" if contract.effective_date else None,
        f"Initial term: {_period(contract.initial_term_amount, contract.initial_term_unit)}"
        if contract.initial_term_amount
        else None,
        "Auto-renews: "
        + ("yes" if contract.auto_renews else "no")
        + (
            f" ({_period(contract.renewal_term_amount, contract.renewal_term_unit)})"
            if contract.auto_renews and contract.renewal_term_amount
            else ""
        )
        if contract.auto_renews is not None
        else None,
        f"Fixed end date: {contract.end_date}" if contract.end_date else None,
        f"Governing law: {contract.governing_law}" if contract.governing_law else None,
        "Key terms reviewed by a user: " + ("yes" if contract.reviewed_at else "no"),
    ]
    upcoming = [d for d in deadlines if d.status == DeadlineStatus.OPEN][:8]
    if upcoming:
        parts.append(
            "Upcoming calculated deadlines: "
            + "; ".join(
                f"{d.label} on {d.due_date}" + ("" if d.confirmed else " (unconfirmed)")
                for d in upcoming
            )
        )
    return ". ".join(p for p in parts if p)


def _clause_text(c: Clause) -> str:
    head = " ".join(x for x in (c.number, c.heading) if x)
    page = f" (p. {c.page_start})" if c.page_start else ""
    if head and c.heading:
        return f"[{c.ref}{page}] {head}\n{c.text}".strip()
    return f"[{c.ref}{page}] {c.text}".strip()


def _ready_documents(db: Session, contract_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """contract_id -> its latest processed document id."""
    rows = db.execute(
        select(Document.contract_id, Document.id)
        .where(Document.contract_id.in_(contract_ids), Document.status == DocumentStatus.READY)
        .order_by(Document.created_at)
    ).all()
    return {contract_id: doc_id for contract_id, doc_id in rows}


def _deadlines_by_contract(
    db: Session, contract_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Deadline]]:
    out: dict[uuid.UUID, list[Deadline]] = {cid: [] for cid in contract_ids}
    today = date.today()
    for d in db.scalars(
        select(Deadline)
        .where(Deadline.contract_id.in_(contract_ids), Deadline.due_date >= today)
        .order_by(Deadline.due_date)
    ):
        out[d.contract_id].append(d)
    return out


def build_sources(
    db: Session, contracts: list[Contract], question: str, single: bool
) -> list[SourceDoc]:
    if not contracts:
        return []
    ids = [c.id for c in contracts]
    docs = _ready_documents(db, ids)
    deadlines = _deadlines_by_contract(db, ids)
    by_id = {c.id: c for c in contracts}

    clauses_by_contract: dict[uuid.UUID, list[Clause]] = {cid: [] for cid in ids}
    doc_ids = list(docs.values())
    total = (
        db.scalar(
            select(func.coalesce(func.sum(func.length(Clause.text)), 0)).where(
                Clause.document_id.in_(doc_ids)
            )
        )
        if doc_ids
        else 0
    )
    doc_to_contract = {v: k for k, v in docs.items()}
    if single or (total or 0) <= MAX_FULL_TEXT_CHARS:
        selected = list(
            db.scalars(
                select(Clause).where(Clause.document_id.in_(doc_ids)).order_by(Clause.ordinal)
            )
        )
    else:
        vector = func.to_tsvector("english", func.coalesce(Clause.heading, "") + " " + Clause.text)
        query = func.websearch_to_tsquery("english", question)
        ranked = (
            select(Clause)
            .where(Clause.document_id.in_(doc_ids), vector.op("@@")(query))
            .order_by(func.ts_rank(vector, query).desc())
            .limit(MAX_SEARCH_CLAUSES)
        )
        selected = sorted(db.scalars(ranked), key=lambda c: (str(c.document_id), c.ordinal))
    for clause in selected:
        clauses_by_contract[doc_to_contract[clause.document_id]].append(clause)

    sources: list[SourceDoc] = []
    if not single:
        lines: list[str] = []
        line_contracts: list[uuid.UUID | None] = []
        for c in contracts:
            lines.append(f"{c.title}: {_facts(c, deadlines[c.id])}")
            line_contracts.append(c.id)
        sources.append(
            SourceDoc(
                contract_id=None,
                title="Portfolio overview (calculated by the system)",
                context="One entry per contract in this workspace.",
                blocks=lines,
                refs=[None] * len(lines),
                block_contract_ids=line_contracts,
            )
        )
    for cid, clauses in clauses_by_contract.items():
        contract = by_id[cid]
        if not clauses:
            continue
        sources.append(
            SourceDoc(
                contract_id=cid,
                title=contract.title,
                context=_facts(contract, deadlines[cid]),
                blocks=[_clause_text(c) for c in clauses],
                refs=[c.ref for c in clauses],
                block_contract_ids=[cid for _ in clauses],
            )
        )
    return sources


def resolve_citations(
    raw: list[dict[str, Any]], sources: list[SourceDoc], titles: dict[uuid.UUID, str]
) -> list[dict[str, Any]]:
    """Map Claude's block-range citations to contracts and clause refs."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for c in raw:
        idx = c.get("document_index")
        if not isinstance(idx, int) or not 0 <= idx < len(sources):
            continue
        src = sources[idx]
        start, end = c.get("start_block_index", 0), c.get("end_block_index", 0)
        refs = tuple(r for r in src.refs[start:end] if r)
        contract_ids = {cid for cid in src.block_contract_ids[start:end] if cid}
        for cid in contract_ids or ({src.contract_id} if src.contract_id else set()):
            key = (str(cid), refs)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "contract_id": str(cid),
                    "contract_title": titles.get(cid, src.title),
                    "clause_refs": list(refs),
                    "cited_text": (c.get("cited_text") or "")[:1000],
                }
            )
    return out


def history_params(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Previous turns as plain text (documents are re-sent with each new question)."""
    params = []
    for m in messages[-HISTORY_MESSAGES:]:
        text = "".join(b.get("text", "") for b in m.blocks).strip()
        if text and m.role in ("user", "assistant") and not m.error:
            params.append({"role": m.role, "content": text})
    # The API needs alternating turns starting with the user.
    while params and params[0]["role"] != "user":
        params.pop(0)
    merged: list[dict[str, Any]] = []
    for p in params:
        if merged and merged[-1]["role"] == p["role"]:
            merged[-1]["content"] += "\n\n" + p["content"]
        else:
            merged.append(p)
    if merged and merged[-1]["role"] == "user":
        merged.pop()  # an unanswered question; the new one replaces it
    return merged


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class ChatResult:
    blocks: list[dict[str, Any]]  # [{"text": str, "citations": [raw citation dicts]}]
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ChatModel(Protocol):
    model: str

    def stream(self, system: str, messages: list[dict[str, Any]]) -> Iterator[str | ChatResult]: ...


class ChatError(RuntimeError):
    pass


class ClaudeChat:
    def __init__(self, api_key: str, model: str, effort: str) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.effort = effort

    def stream(self, system: str, messages: list[dict[str, Any]]) -> Iterator[str | ChatResult]:
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            output_config={"effort": self.effort},  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text
            message = stream.get_final_message()
        if message.stop_reason == "refusal":
            raise ChatError("The AI model declined to answer this question")
        blocks = []
        for block in message.content:
            if block.type != "text":
                continue
            citations = [
                c.model_dump()
                for c in (block.citations or [])
                if c.type == "content_block_location"
            ]
            blocks.append({"text": block.text, "citations": citations})
        yield ChatResult(
            blocks=blocks,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )


@lru_cache
def get_chat_model() -> ChatModel:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ChatError("AI chat is not configured (ANTHROPIC_API_KEY is not set)")
    return ClaudeChat(settings.anthropic_api_key, settings.anthropic_model, settings.chat_effort)
