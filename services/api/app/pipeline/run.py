"""Document processing pipeline: parse → segment → extract → apply → compute deadlines."""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, set_tenant
from app.models import (
    Clause,
    Contract,
    ContractStatus,
    DateRule,
    Document,
    DocumentStatus,
    ExtractionRun,
    Organization,
    PaymentTerm,
    ReviewStatus,
    Workspace,
)
from app.pipeline import extract as ext
from app.pipeline.compute import refresh_deadlines
from app.pipeline.parse import Page, parse
from app.pipeline.segment import segment
from app.storage import get_storage

log = logging.getLogger(__name__)

MAX_OCR_PAGES = 100

# Contract fields filled from the extraction: name -> how to read it.
_SOURCED_FIELDS = (
    "effective_date",
    "end_date",
    "initial_term",
    "auto_renews",
    "renewal_term",
    "governing_law",
    "contract_value",
    "notice_details",
)


def _source_dict(source: ext.Source, valid_refs: set[str]) -> dict[str, Any]:
    return {
        "clause_refs": [r for r in source.clause_refs if r in valid_refs],
        "quote": source.quote,
        "confidence": max(0.0, min(1.0, source.confidence)),
        "status": ReviewStatus.AI_SUGGESTED.value,
    }


def _locked(contract: Contract, field: str) -> bool:
    """A field the user has reviewed must not be overwritten by a re-run."""
    status = (contract.field_sources or {}).get(field, {}).get("status")
    return status in (ReviewStatus.CONFIRMED, ReviewStatus.EDITED)


def apply_extraction(
    db: Session, contract: Contract, data: ext.ContractExtraction, valid_refs: set[str]
) -> None:
    sources: dict[str, Any] = dict(contract.field_sources or {})

    def set_field(name: str, item: Any, assign: Any) -> None:
        if _locked(contract, name):
            return
        if item is None:
            assign(None)
            sources.pop(name, None)
            return
        assign(item.value)
        sources[name] = _source_dict(item.source, valid_refs)

    if not _locked(contract, "title") and data.title:
        contract.title = data.title[:500]
    contract.contract_type = data.contract_type[:100] if data.contract_type else None
    contract.summary = data.summary
    contract.parties = [p.model_dump() for p in data.parties]
    if not _locked(contract, "counterparty_name"):
        contract.counterparty_name = data.counterparty_name
    if not _locked(contract, "currency"):
        contract.currency = (data.currency or "").upper()[:3] or None

    def set_period(prefix: str):
        def assign(value: ext.Period | None) -> None:
            setattr(contract, f"{prefix}_amount", value.amount if value else None)
            setattr(contract, f"{prefix}_unit", value.unit if value else None)

        return assign

    set_field(
        "effective_date", data.effective_date, lambda v: setattr(contract, "effective_date", v)
    )
    set_field("end_date", data.end_date, lambda v: setattr(contract, "end_date", v))
    set_field("initial_term", data.initial_term, set_period("initial_term"))
    set_field("auto_renews", data.auto_renews, lambda v: setattr(contract, "auto_renews", v))
    set_field("renewal_term", data.renewal_term, set_period("renewal_term"))
    set_field(
        "governing_law",
        data.governing_law,
        lambda v: setattr(contract, "governing_law", v[:200] if v else None),
    )
    set_field(
        "contract_value",
        data.contract_value,
        lambda v: setattr(contract, "contract_value", Decimal(str(v)) if v is not None else None),
    )
    set_field(
        "notice_details", data.notice_details, lambda v: setattr(contract, "notice_details", v)
    )
    contract.field_sources = sources

    # Replace previous AI suggestions; keep anything a user has reviewed or added.
    for rule in list(contract.date_rules):
        if rule.review_status == ReviewStatus.AI_SUGGESTED:
            contract.date_rules.remove(rule)
    for term in list(contract.payment_terms):
        if term.review_status == ReviewStatus.AI_SUGGESTED:
            contract.payment_terms.remove(term)
    db.flush()

    # Don't re-suggest what a user already reviewed (confirmed, edited or rejected).
    reviewed_rules = {(r.rule_type, r.anchor) for r in contract.date_rules}
    reviewed_payments = [
        (p.frequency, p.description.lower(), set(p.source_clause_refs))
        for p in contract.payment_terms
    ]

    def payment_reviewed(p: ext.ExtractedPaymentTerm, refs: list[str]) -> bool:
        return any(
            freq == p.frequency and (desc == p.description.lower() or old & set(refs))
            for freq, desc, old in reviewed_payments
        )

    scope = {"organization_id": contract.organization_id, "workspace_id": contract.workspace_id}
    for r in data.date_rules:
        if (r.rule_type, r.anchor) in reviewed_rules:
            continue
        src = _source_dict(r.source, valid_refs)
        contract.date_rules.append(
            DateRule(
                **scope,
                rule_type=r.rule_type,
                label=r.label[:300],
                anchor=r.anchor,
                fixed_date=r.fixed_date,
                offset_amount=r.offset.amount if r.offset else None,
                offset_unit=r.offset.unit if r.offset else None,
                offset_basis=r.offset_basis,
                direction=r.direction,
                delivery_amount=r.deemed_receipt_business_days or None,
                source_clause_refs=src["clause_refs"],
                quote=src["quote"],
                confidence=src["confidence"],
            )
        )
    for p in data.payment_terms:
        src = _source_dict(p.source, valid_refs)
        if payment_reviewed(p, src["clause_refs"]):
            continue
        contract.payment_terms.append(
            PaymentTerm(
                **scope,
                description=p.description[:500],
                direction=p.direction,
                amount=Decimal(str(p.amount)) if p.amount is not None else None,
                currency=(p.currency or contract.currency or "").upper()[:3] or None,
                frequency=p.frequency,
                first_due_date=p.first_due_date,
                payment_days=p.payment_days,
                escalation=p.escalation,
                source_clause_refs=src["clause_refs"],
                quote=src["quote"],
                confidence=src["confidence"],
            )
        )


def _context(org: Organization, workspace: Workspace) -> str:
    return (
        f"Context: the user's organization is '{org.name}' ({org.kind.replace('_', ' ')}). "
        f"This contract is filed under the workspace '{workspace.name}' "
        f"({workspace.kind}). The user's side of the contract is most likely the party "
        "matching one of these names; the other party is the counterparty."
    )


def process_document(org_id: uuid.UUID, document_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        set_tenant(db, org_id)
        doc = db.get(Document, document_id)
        if doc is None:
            log.warning("Document %s not found", document_id)
            return
        doc.status = DocumentStatus.PROCESSING
        doc.error = None
        db.commit()
        try:
            _process(db, doc)
            doc.status = DocumentStatus.READY
            doc.processed_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:
            db.rollback()
            log.exception("Processing document %s failed", document_id)
            doc = db.get(Document, document_id)
            assert doc is not None
            doc.status = DocumentStatus.FAILED
            doc.error = (
                str(exc)
                if isinstance(exc, ext.ExtractionError | ValueError)
                else ("Unexpected error while analysing the document")
            )
            contract = db.get(Contract, doc.contract_id)
            if contract and contract.status == ContractStatus.PROCESSING:
                contract.status = ContractStatus.NEEDS_REVIEW
            db.commit()


def _process(db: Session, doc: Document) -> None:
    data = get_storage().get(doc.storage_key)
    parsed = parse(data, doc.mime_type)
    doc.page_count = parsed.page_count
    pages = parsed.pages
    if parsed.text_source == "needs_ocr":
        if (parsed.page_count or 0) > MAX_OCR_PAGES:
            raise ValueError(f"Scanned documents are limited to {MAX_OCR_PAGES} pages for now")
        pages = [Page(p.page_number, p.text) for p in ext.get_extractor().transcribe_pdf(data)]
        doc.text_source = "ocr"
    else:
        doc.text_source = parsed.text_source
    if not "".join(p.text for p in pages).strip():
        raise ValueError("No text could be read from this document")

    db.execute(delete(Clause).where(Clause.document_id == doc.id))
    drafts = segment(pages)
    clauses = [
        Clause(
            organization_id=doc.organization_id,
            workspace_id=doc.workspace_id,
            document_id=doc.id,
            ref=f"C{i}",
            ordinal=i,
            number=d.number[:50] if d.number else None,
            heading=d.heading[:500] if d.heading else None,
            text=d.text,
            page_start=d.page_start,
            page_end=d.page_end,
        )
        for i, d in enumerate(drafts, start=1)
    ]
    db.add_all(clauses)
    db.flush()

    contract = db.get(Contract, doc.contract_id)
    org = db.get(Organization, doc.organization_id)
    workspace = db.get(Workspace, doc.workspace_id)
    assert contract and org and workspace

    extractor = ext.get_extractor()
    xml = ext.render_clauses([(c.ref, c.number, c.heading, c.page_start, c.text) for c in clauses])
    run = ExtractionRun(
        organization_id=doc.organization_id,
        document_id=doc.id,
        model=extractor.model,
        prompt_version=ext.PROMPT_VERSION,
        status="failed",
    )
    db.add(run)
    try:
        result = extractor.extract(xml, _context(org, workspace))
    except Exception as exc:
        run.error = str(exc)[:2000]
        db.commit()  # keep the failed run for diagnosis
        raise
    run.status = "succeeded"
    run.model = result.model
    run.input_tokens = result.input_tokens
    run.output_tokens = result.output_tokens
    run.output = result.extraction.model_dump(mode="json")

    apply_extraction(db, contract, result.extraction, {c.ref for c in clauses})
    if contract.status == ContractStatus.PROCESSING:
        contract.status = ContractStatus.NEEDS_REVIEW
    db.flush()
    db.refresh(contract)
    refresh_deadlines(db, contract, org.default_country)


def latest_clauses(db: Session, document_id: uuid.UUID) -> list[Clause]:
    return list(
        db.scalars(select(Clause).where(Clause.document_id == document_id).order_by(Clause.ordinal))
    )
