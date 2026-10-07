import hashlib
import re
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import audit
from app.config import get_settings
from app.contract_schemas import (
    CONTRACT_EDITABLE,
    FIELD_OF_COLUMN,
    ClauseOut,
    ContractCreate,
    ContractDetail,
    ContractSummary,
    ContractUpdate,
    DateRuleIn,
    DateRuleOut,
    DateRuleUpdate,
    DeadlineOut,
    DeadlineUpdate,
    DeadlineWithContract,
    PaymentTermIn,
    PaymentTermOut,
    PaymentTermUpdate,
)
from app.deps import OrgContext, get_org_context
from app.models import (
    Clause,
    Contract,
    ContractStatus,
    DateRule,
    Deadline,
    DeadlineStatus,
    Document,
    DocumentStatus,
    OrganizationMembership,
    PaymentTerm,
    ReviewStatus,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from app.pipeline.compute import refresh_deadlines
from app.pipeline.parse import UnsupportedDocument, sniff_mime_type
from app.pipeline.run import MANUAL
from app.reminders import accessible_workspace_ids
from app.storage import get_storage
from app.workers.tasks import enqueue_document

router = APIRouter(prefix="/organizations/{org_id}", tags=["contracts"])

_REVIEWED = (ReviewStatus.CONFIRMED, ReviewStatus.EDITED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_contract(
    ctx: OrgContext, contract_id: uuid.UUID, min_role: WorkspaceRole = WorkspaceRole.VIEWER
) -> Contract:
    contract = ctx.db.get(Contract, contract_id)
    if contract is None or contract.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    try:
        ctx.get_workspace(contract.workspace_id, min_role)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found") from exc
        raise
    return contract


def _pending_review(contract: Contract) -> int:
    pending = sum(
        1 for r in contract.date_rules if r.review_status == ReviewStatus.AI_SUGGESTED
    ) + sum(1 for p in contract.payment_terms if p.review_status == ReviewStatus.AI_SUGGESTED)
    if contract.reviewed_at is None and contract.field_sources:
        pending += 1
    return pending


def _next_deadline(contract: Contract) -> Deadline | None:
    today = date.today()
    upcoming = [
        d for d in contract.deadlines if d.status == DeadlineStatus.OPEN and d.due_date >= today
    ]
    return min(upcoming, key=lambda d: d.due_date, default=None)


def _summary(contract: Contract) -> ContractSummary:
    out = ContractSummary.model_validate(contract)
    nd = _next_deadline(contract)
    out.next_deadline = DeadlineOut.model_validate(nd) if nd else None
    out.pending_review = _pending_review(contract)
    return out


def _detail(contract: Contract) -> ContractDetail:
    out = ContractDetail.model_validate(contract)
    nd = _next_deadline(contract)
    out.next_deadline = DeadlineOut.model_validate(nd) if nd else None
    out.pending_review = _pending_review(contract)
    return out


def _recompute(ctx: OrgContext, contract: Contract) -> None:
    ctx.db.flush()
    ctx.db.refresh(contract)
    refresh_deadlines(ctx.db, contract, ctx.membership.organization.default_country)


def _check_owner(ctx: OrgContext, contract: Contract, user_id: uuid.UUID) -> None:
    """The owner must be able to see the contract."""
    membership = ctx.db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == ctx.org_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    allowed = accessible_workspace_ids(ctx.db, membership) if membership else set()
    if allowed is not None and contract.workspace_id not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The owner must have access to this workspace"
        )


def _safe_filename(name: str) -> str:
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return re.sub(r"[^\w.\- ]", "_", name).strip() or "document"


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


async def _read_upload(file: UploadFile) -> tuple[bytes, str, str, str]:
    """Validate an uploaded file: returns (data, filename, mime type, sha256)."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Files are limited to {limit // 1024**2} MB"
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")
    filename = _safe_filename(file.filename or "document")
    try:
        mime_type = sniff_mime_type(data, filename)
    except UnsupportedDocument as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    return data, filename, mime_type, hashlib.sha256(data).hexdigest()


def _reject_duplicate(ctx: OrgContext, workspace_id: uuid.UUID, sha256: str) -> None:
    duplicate = ctx.db.scalar(
        select(Document).where(Document.workspace_id == workspace_id, Document.sha256 == sha256)
    )
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "This file has already been uploaded to this workspace",
                "contract_id": str(duplicate.contract_id),
            },
        )


def _store_document(
    ctx: OrgContext, contract: Contract, data: bytes, filename: str, mime_type: str, sha256: str
) -> Document:
    document_id = uuid.uuid4()
    key = f"{ctx.org_id}/{contract.workspace_id}/{contract.id}/{document_id}/{filename}"
    get_storage().put(key, data, mime_type)
    document = Document(
        id=document_id,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        contract_id=contract.id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=sha256,
        storage_key=key,
        status=DocumentStatus.UPLOADED,
    )
    ctx.db.add(document)
    return document


@router.post(
    "/workspaces/{workspace_id}/contracts", response_model=ContractSummary, status_code=201
)
async def upload_contract(
    workspace_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    ctx: OrgContext = Depends(get_org_context),
) -> ContractSummary:
    """Upload a contract document; it is analysed in the background."""
    workspace = ctx.get_workspace(workspace_id, WorkspaceRole.EDITOR)
    data, filename, mime_type, sha256 = await _read_upload(file)
    _reject_duplicate(ctx, workspace.id, sha256)
    contract = Contract(
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        title=(title or filename.rsplit(".", 1)[0])[:500],
        status=ContractStatus.PROCESSING,
        created_by_id=ctx.user.id,
        owner_id=ctx.user.id,
    )
    ctx.db.add(contract)
    ctx.db.flush()
    document = _store_document(ctx, contract, data, filename, mime_type, sha256)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        actor_user_id=ctx.user.id,
        action="contract.uploaded",
        entity_type="contract",
        entity_id=contract.id,
        data={"filename": filename, "size_bytes": len(data)},
    )
    ctx.db.commit()
    ctx.db.refresh(contract)
    enqueue_document(background, ctx.org_id, document.id)
    return _summary(contract)


@router.post(
    "/workspaces/{workspace_id}/contracts/manual",
    response_model=ContractDetail,
    status_code=201,
)
def create_contract_manually(
    workspace_id: uuid.UUID, body: ContractCreate, ctx: OrgContext = Depends(get_org_context)
) -> ContractDetail:
    """Create a contract from typed-in terms (no document needed). What the user enters
    counts as reviewed: deadlines are confirmed and AI analysis never overwrites it."""
    workspace = ctx.get_workspace(workspace_id, WorkspaceRole.EDITOR)
    fields = body.model_dump(exclude={"date_rules", "payment_terms", "owner_id"})
    now = datetime.now(UTC)
    contract = Contract(
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        status=ContractStatus.ACTIVE,
        created_by_id=ctx.user.id,
        owner_id=ctx.user.id,
        reviewed_at=now,
        reviewed_by_id=ctx.user.id,
        **fields,
    )
    entered = {FIELD_OF_COLUMN.get(k, k) for k, v in fields.items() if v is not None}
    contract.field_sources = {
        f: {"clause_refs": [], "quote": None, "confidence": None, "status": MANUAL}
        for f in sorted(entered)
    }
    ctx.db.add(contract)
    ctx.db.flush()
    if body.owner_id:
        _check_owner(ctx, contract, body.owner_id)
        contract.owner_id = body.owner_id
    scope = {"organization_id": ctx.org_id, "workspace_id": workspace.id}
    review = {
        "review_status": ReviewStatus.CONFIRMED,
        "reviewed_at": now,
        "reviewed_by_id": ctx.user.id,
    }
    for rule in body.date_rules:
        contract.date_rules.append(
            DateRule(**scope, **rule.model_dump(), source_clause_refs=[], **review)
        )
    for term in body.payment_terms:
        contract.payment_terms.append(
            PaymentTerm(**scope, **term.model_dump(), source_clause_refs=[], **review)
        )
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        actor_user_id=ctx.user.id,
        action="contract.created_manually",
        entity_type="contract",
        entity_id=contract.id,
        data=body.model_dump(mode="json"),
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    ctx.db.refresh(contract)
    return _detail(contract)


@router.post("/contracts/{contract_id}/documents", response_model=ContractDetail, status_code=201)
async def attach_document(
    contract_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    ctx: OrgContext = Depends(get_org_context),
) -> ContractDetail:
    """Attach the signed document to an existing contract (e.g. one entered by hand). If
    AI analysis is configured it runs, but terms a user entered or reviewed are kept."""
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    data, filename, mime_type, sha256 = await _read_upload(file)
    _reject_duplicate(ctx, contract.workspace_id, sha256)
    document = _store_document(ctx, contract, data, filename, mime_type, sha256)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="contract.document_attached",
        entity_type="contract",
        entity_id=contract.id,
        data={"filename": filename, "size_bytes": len(data)},
    )
    ctx.db.commit()
    ctx.db.refresh(contract)
    enqueue_document(background, ctx.org_id, document.id)
    return _detail(contract)


@router.get("/workspaces/{workspace_id}/contracts", response_model=list[ContractSummary])
def list_contracts(
    workspace_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> list[ContractSummary]:
    ctx.get_workspace(workspace_id)
    contracts = ctx.db.scalars(
        select(Contract)
        .where(Contract.workspace_id == workspace_id)
        .options(
            selectinload(Contract.documents),
            selectinload(Contract.deadlines),
            selectinload(Contract.date_rules),
            selectinload(Contract.payment_terms),
        )
        .order_by(Contract.created_at.desc())
    )
    return [_summary(c) for c in contracts]


@router.get("/contracts/{contract_id}", response_model=ContractDetail)
def get_contract(
    contract_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> ContractDetail:
    return _detail(_get_contract(ctx, contract_id))


@router.patch("/contracts/{contract_id}", response_model=ContractDetail)
def update_contract(
    contract_id: uuid.UUID, body: ContractUpdate, ctx: OrgContext = Depends(get_org_context)
) -> ContractDetail:
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    changes = body.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        owner_id = changes.pop("owner_id")
        if owner_id is not None:
            _check_owner(ctx, contract, owner_id)
        contract.owner_id = owner_id
    sources = dict(contract.field_sources or {})
    for column, value in changes.items():
        if column not in CONTRACT_EDITABLE:
            continue
        setattr(contract, column, value)
        field = FIELD_OF_COLUMN.get(column, column)
        entry = dict(sources.get(field) or {"clause_refs": [], "quote": None, "confidence": None})
        entry["status"] = ReviewStatus.EDITED.value
        sources[field] = entry
    contract.field_sources = sources
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="contract.updated",
        entity_type="contract",
        entity_id=contract.id,
        data=body.model_dump(mode="json", exclude_unset=True),
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    return _detail(contract)


@router.post("/contracts/{contract_id}/confirm-terms", response_model=ContractDetail)
def confirm_terms(
    contract_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> ContractDetail:
    """Confirm the contract-level terms (dates, term, renewal) as reviewed."""
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    sources = {}
    for field, entry in (contract.field_sources or {}).items():
        entry = dict(entry)
        if entry.get("status") == ReviewStatus.AI_SUGGESTED:
            entry["status"] = ReviewStatus.CONFIRMED.value
        sources[field] = entry
    contract.field_sources = sources
    contract.reviewed_at = datetime.now(UTC)
    contract.reviewed_by_id = ctx.user.id
    if contract.status in (ContractStatus.PROCESSING, ContractStatus.NEEDS_REVIEW):
        contract.status = ContractStatus.ACTIVE
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="contract.terms_confirmed",
        entity_type="contract",
        entity_id=contract.id,
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    return _detail(contract)


@router.post("/contracts/{contract_id}/reprocess", response_model=ContractDetail)
def reprocess_contract(
    contract_id: uuid.UUID,
    background: BackgroundTasks,
    ctx: OrgContext = Depends(get_org_context),
) -> ContractDetail:
    """Run the AI analysis again. Values a user has reviewed are kept."""
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    if not contract.documents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The contract has no document")
    document = contract.documents[-1]
    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "The document is already being processed")
    document.status = DocumentStatus.UPLOADED
    document.error = None
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="contract.reprocessed",
        entity_type="contract",
        entity_id=contract.id,
    )
    ctx.db.commit()
    enqueue_document(background, ctx.org_id, document.id)
    return _detail(contract)


@router.delete("/contracts/{contract_id}", status_code=204)
def delete_contract(contract_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)) -> None:
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    keys = [d.storage_key for d in contract.documents]
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="contract.deleted",
        entity_type="contract",
        entity_id=contract.id,
        data={"title": contract.title},
    )
    ctx.db.delete(contract)
    ctx.db.commit()
    storage = get_storage()
    for key in keys:
        storage.delete(key)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def _get_document(ctx: OrgContext, document_id: uuid.UUID) -> Document:
    document = ctx.db.get(Document, document_id)
    if document is None or document.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _get_contract(ctx, document.contract_id)
    return document


@router.get("/documents/{document_id}/file")
def download_document(
    document_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> Response:
    document = _get_document(ctx, document_id)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=document.workspace_id,
        actor_user_id=ctx.user.id,
        action="document.viewed",
        entity_type="document",
        entity_id=document.id,
    )
    ctx.db.commit()
    return Response(
        content=get_storage().get(document.storage_key),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/documents/{document_id}/clauses", response_model=list[ClauseOut])
def list_clauses(
    document_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> list[Clause]:
    document = _get_document(ctx, document_id)
    return list(
        ctx.db.scalars(
            select(Clause).where(Clause.document_id == document.id).order_by(Clause.ordinal)
        )
    )


# ---------------------------------------------------------------------------
# Date rules & payment terms (review and manual entry)
# ---------------------------------------------------------------------------


def _apply_review(item: DateRule | PaymentTerm, changes: dict, ctx: OrgContext) -> None:
    decision = changes.pop("review_status", None)
    for key, value in changes.items():
        setattr(item, key, value)
    if changes:
        item.review_status = ReviewStatus.EDITED
    elif decision is not None:
        item.review_status = decision
    item.reviewed_at = datetime.now(UTC)
    item.reviewed_by_id = ctx.user.id


@router.post("/contracts/{contract_id}/date-rules", response_model=DateRuleOut, status_code=201)
def create_date_rule(
    contract_id: uuid.UUID, body: DateRuleIn, ctx: OrgContext = Depends(get_org_context)
) -> DateRule:
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    rule = DateRule(
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        contract_id=contract.id,
        **body.model_dump(),
        source_clause_refs=[],
        review_status=ReviewStatus.CONFIRMED,
        reviewed_at=datetime.now(UTC),
        reviewed_by_id=ctx.user.id,
    )
    contract.date_rules.append(rule)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="date_rule.created",
        entity_type="contract",
        entity_id=contract.id,
        data=body.model_dump(mode="json"),
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    ctx.db.refresh(rule)
    return rule


@router.patch("/date-rules/{rule_id}", response_model=DateRuleOut)
def update_date_rule(
    rule_id: uuid.UUID, body: DateRuleUpdate, ctx: OrgContext = Depends(get_org_context)
) -> DateRule:
    rule = ctx.db.get(DateRule, rule_id)
    if rule is None or rule.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Date rule not found")
    contract = _get_contract(ctx, rule.contract_id, WorkspaceRole.EDITOR)
    changes = body.model_dump(exclude_unset=True)
    _apply_review(rule, dict(changes), ctx)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="date_rule.reviewed",
        entity_type="date_rule",
        entity_id=rule.id,
        data=body.model_dump(mode="json", exclude_unset=True),
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    ctx.db.refresh(rule)
    return rule


@router.post(
    "/contracts/{contract_id}/payment-terms", response_model=PaymentTermOut, status_code=201
)
def create_payment_term(
    contract_id: uuid.UUID, body: PaymentTermIn, ctx: OrgContext = Depends(get_org_context)
) -> PaymentTerm:
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    term = PaymentTerm(
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        contract_id=contract.id,
        **body.model_dump(),
        source_clause_refs=[],
        review_status=ReviewStatus.CONFIRMED,
        reviewed_at=datetime.now(UTC),
        reviewed_by_id=ctx.user.id,
    )
    contract.payment_terms.append(term)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="payment_term.created",
        entity_type="contract",
        entity_id=contract.id,
        data=body.model_dump(mode="json"),
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    ctx.db.refresh(term)
    return term


@router.patch("/payment-terms/{term_id}", response_model=PaymentTermOut)
def update_payment_term(
    term_id: uuid.UUID, body: PaymentTermUpdate, ctx: OrgContext = Depends(get_org_context)
) -> PaymentTerm:
    term = ctx.db.get(PaymentTerm, term_id)
    if term is None or term.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment term not found")
    contract = _get_contract(ctx, term.contract_id, WorkspaceRole.EDITOR)
    _apply_review(term, body.model_dump(exclude_unset=True), ctx)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="payment_term.reviewed",
        entity_type="payment_term",
        entity_id=term.id,
        data=body.model_dump(mode="json", exclude_unset=True),
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    ctx.db.refresh(term)
    return term


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------


@router.get("/deadlines", response_model=list[DeadlineWithContract])
def list_deadlines(
    ctx: OrgContext = Depends(get_org_context),
    workspace_id: uuid.UUID | None = None,
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    include_closed: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[DeadlineWithContract]:
    """Deadlines across every workspace the user can access."""
    start = start or date.today() - timedelta(days=30)
    query = (
        select(Deadline, Contract, Workspace)
        .join(Contract, Contract.id == Deadline.contract_id)
        .join(Workspace, Workspace.id == Deadline.workspace_id)
        .where(Deadline.organization_id == ctx.org_id, Deadline.due_date >= start)
        .order_by(Deadline.due_date, Deadline.label)
        .limit(limit)
    )
    if end:
        query = query.where(Deadline.due_date <= end)
    if not include_closed:
        query = query.where(Deadline.status == DeadlineStatus.OPEN)
    if workspace_id:
        ctx.get_workspace(workspace_id)
        query = query.where(Deadline.workspace_id == workspace_id)
    elif not ctx.is_org_admin:
        query = query.where(
            Deadline.workspace_id.in_(
                select(WorkspaceMembership.workspace_id).where(
                    WorkspaceMembership.user_id == ctx.user.id
                )
            )
        )
    return [
        DeadlineWithContract(
            **DeadlineOut.model_validate(d).model_dump(),
            contract_title=c.title,
            counterparty_name=c.counterparty_name,
            workspace_name=w.name,
        )
        for d, c, w in ctx.db.execute(query)
    ]


@router.patch("/deadlines/{deadline_id}", response_model=DeadlineOut)
def update_deadline(
    deadline_id: uuid.UUID, body: DeadlineUpdate, ctx: OrgContext = Depends(get_org_context)
) -> Deadline:
    deadline = ctx.db.get(Deadline, deadline_id)
    if deadline is None or deadline.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deadline not found")
    _get_contract(ctx, deadline.contract_id, WorkspaceRole.EDITOR)
    changes = body.model_dump(exclude_unset=True)
    if "decision" in changes:
        deadline.decision = body.decision
        deadline.decision_note = body.decision_note if body.decision else None
        deadline.decided_at = datetime.now(UTC) if body.decision else None
        deadline.decided_by_id = ctx.user.id if body.decision else None
        if body.decision and "status" not in changes:
            deadline.status = DeadlineStatus.DONE
    elif "decision_note" in changes and deadline.decision:
        deadline.decision_note = body.decision_note
    if body.status is not None:
        deadline.status = body.status
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=deadline.workspace_id,
        actor_user_id=ctx.user.id,
        action="deadline.decision_recorded" if "decision" in changes else "deadline.status_changed",
        entity_type="deadline",
        entity_id=deadline.id,
        data={
            "label": deadline.label,
            "due_date": deadline.due_date.isoformat(),
            **body.model_dump(mode="json", exclude_unset=True),
        },
    )
    ctx.db.commit()
    return deadline
