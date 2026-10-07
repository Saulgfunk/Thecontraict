"""Applying and reverting contract amendments.

An amendment's changes are applied to the contract straight away, so the contract always
shows the terms currently in force and deadlines are calculated from them. Each change
keeps the previous value, which lets the UI show "before → after" and lets an amendment
recorded by mistake be undone.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Amendment,
    AmendmentChange,
    Contract,
    DateRule,
    PaymentTerm,
    ReviewStatus,
)

# field_sources status for a term set by an amendment (never overwritten by AI analysis).
AMENDED = "amended"

CONTRACT_FIELDS = (
    "title",
    "counterparty_name",
    "contract_type",
    "end_date",
    "initial_term_amount",
    "initial_term_unit",
    "auto_renews",
    "renewal_term_amount",
    "renewal_term_unit",
    "governing_law",
    "holiday_country",
    "currency",
    "contract_value",
    "notice_details",
)
RULE_FIELDS = (
    "label",
    "anchor",
    "fixed_date",
    "offset_amount",
    "offset_unit",
    "offset_basis",
    "direction",
    "delivery_amount",
)
PAYMENT_FIELDS = (
    "description",
    "direction",
    "amount",
    "currency",
    "frequency",
    "first_due_date",
    "payment_days",
    "escalation",
)
FIELD_GROUP = {
    "initial_term_amount": "initial_term",
    "initial_term_unit": "initial_term",
    "renewal_term_amount": "renewal_term",
    "renewal_term_unit": "renewal_term",
}


def to_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def from_json(obj: Any, column: str, value: Any) -> Any:
    """Convert a stored JSON value back to the column's Python type."""
    if value is None:
        return None
    python_type = type(obj).__table__.c[column].type.python_type
    if python_type is date:
        return date.fromisoformat(value)
    if python_type is Decimal:
        return Decimal(str(value))
    return value


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except ArithmeticError:
        return str(a) == str(b)


@dataclass
class Recorder:
    amendment: Amendment
    changes: list[AmendmentChange] = field(default_factory=list)

    def add(
        self,
        target_type: str,
        target_id: uuid.UUID | None,
        name: str,
        label: str,
        old: Any,
        new: Any,
    ) -> None:
        self.changes.append(
            AmendmentChange(
                organization_id=self.amendment.organization_id,
                amendment_id=self.amendment.id,
                ordinal=len(self.changes),
                target_type=target_type,
                target_id=target_id,
                field=name,
                label=label,
                old_value=old,
                new_value=new,
            )
        )


def _set_fields(
    obj: Any,
    values: dict[str, Any],
    allowed: tuple[str, ...],
    rec: Recorder,
    target_type: str,
    label: str,
) -> list[str]:
    changed = []
    for name, value in values.items():
        if name not in allowed:
            continue
        old = to_json(getattr(obj, name))
        new = to_json(value)
        if _same(old, new):
            continue
        setattr(obj, name, from_json(obj, name, new))
        rec.add(
            target_type,
            getattr(obj, "id", None) if target_type != "contract" else None,
            name,
            label,
            old,
            new,
        )
        changed.append(name)
    return changed


def apply_amendment(
    db: Session,
    contract: Contract,
    amendment: Amendment,
    contract_changes: dict[str, Any],
    rule_changes: list[dict[str, Any]],
    payment_changes: list[dict[str, Any]],
    new_rules: list[dict[str, Any]],
    new_payments: list[dict[str, Any]],
    user_id: uuid.UUID,
) -> list[AmendmentChange]:
    """Apply the changes to the contract and return the recorded changes."""
    rec = Recorder(amendment)
    changed = _set_fields(contract, contract_changes, CONTRACT_FIELDS, rec, "contract", "Contract")
    sources = dict(contract.field_sources or {})
    for name in changed:
        sources[FIELD_GROUP.get(name, name)] = {
            "clause_refs": [],
            "quote": None,
            "confidence": None,
            "status": AMENDED,
            "amendment_id": str(amendment.id),
            "amendment_title": amendment.title,
        }
    contract.field_sources = sources

    rules = {r.id: r for r in contract.date_rules}
    for change in rule_changes:
        rule = rules.get(change["date_rule_id"])
        if rule is None:
            raise ValueError("The date rule does not belong to this contract")
        values = {k: v for k, v in change.items() if k != "date_rule_id"}
        if _set_fields(rule, values, RULE_FIELDS, rec, "date_rule", rule.label):
            # Entered by a user from a signed amendment: confirmed, not a suggestion.
            rule.review_status = ReviewStatus.CONFIRMED
            rule.reviewed_at = datetime.now(UTC)
            rule.reviewed_by_id = user_id

    payments = {p.id: p for p in contract.payment_terms}
    for change in payment_changes:
        term = payments.get(change["payment_term_id"])
        if term is None:
            raise ValueError("The payment term does not belong to this contract")
        values = {k: v for k, v in change.items() if k != "payment_term_id"}
        if _set_fields(term, values, PAYMENT_FIELDS, rec, "payment_term", term.description):
            term.review_status = ReviewStatus.CONFIRMED
            term.reviewed_at = datetime.now(UTC)
            term.reviewed_by_id = user_id

    scope = {"organization_id": contract.organization_id, "workspace_id": contract.workspace_id}
    review = {
        "review_status": ReviewStatus.CONFIRMED,
        "reviewed_at": datetime.now(UTC),
        "reviewed_by_id": user_id,
        "source_clause_refs": [],
    }
    for values in new_rules:
        rule = DateRule(id=uuid.uuid4(), contract_id=contract.id, **scope, **values, **review)
        contract.date_rules.append(rule)
        rec.add("date_rule", rule.id, "_created", rule.label, None, to_json_dict(values))
    for values in new_payments:
        term = PaymentTerm(id=uuid.uuid4(), contract_id=contract.id, **scope, **values, **review)
        contract.payment_terms.append(term)
        rec.add("payment_term", term.id, "_created", term.description, None, to_json_dict(values))

    for recorded in rec.changes:
        db.add(recorded)
    return rec.changes


def to_json_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {k: to_json(v) for k, v in values.items()}


def revert_amendment(db: Session, contract: Contract, amendment: Amendment) -> list[str]:
    """Undo an amendment's changes. A value changed again since the amendment is left as
    it is and reported, so later edits are never silently lost."""
    conflicts: list[str] = []
    rules = {r.id: r for r in contract.date_rules}
    payments = {p.id: p for p in contract.payment_terms}
    sources = dict(contract.field_sources or {})
    for change in reversed(amendment.changes):
        target: Any
        if change.target_type == "contract":
            target = contract
        elif change.target_type == "date_rule":
            target = rules.get(change.target_id)  # type: ignore[arg-type]
        else:
            target = payments.get(change.target_id)  # type: ignore[arg-type]

        if change.field == "_created":
            if target is not None:
                collection = (
                    contract.date_rules
                    if change.target_type == "date_rule"
                    else contract.payment_terms
                )
                collection.remove(target)
            continue
        if target is None:
            continue  # deleted since; nothing to restore
        current = to_json(getattr(target, change.field))
        if not _same(current, change.new_value):
            conflicts.append(f"{change.label}: {change.field.replace('_', ' ')}")
            continue
        setattr(target, change.field, from_json(target, change.field, change.old_value))
        if change.target_type == "contract":
            key = FIELD_GROUP.get(change.field, change.field)
            source = sources.get(key) or {}
            if source.get("amendment_id") == str(amendment.id):
                sources[key] = {**source, "status": ReviewStatus.EDITED.value}
                sources[key].pop("amendment_id", None)
                sources[key].pop("amendment_title", None)
    contract.field_sources = sources
    db.flush()
    return conflicts
