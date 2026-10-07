import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from app import audit
from app.amendments import apply_amendment, revert_amendment
from app.contract_schemas import (
    AmendmentCreate,
    AmendmentDeleted,
    AmendmentOut,
    AmendmentUpdate,
)
from app.deps import OrgContext, get_org_context
from app.models import Amendment, WorkspaceRole
from app.routers.contracts import (
    _get_contract,
    _read_upload,
    _recompute,
    _reject_duplicate,
    _store_document,
)
from app.storage import get_storage
from app.workers.tasks import enqueue_document

router = APIRouter(prefix="/organizations/{org_id}", tags=["amendments"])


def _get_amendment(
    ctx: OrgContext, amendment_id: uuid.UUID, min_role: WorkspaceRole = WorkspaceRole.VIEWER
) -> Amendment:
    amendment = ctx.db.get(Amendment, amendment_id)
    if amendment is None or amendment.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Amendment not found")
    _get_contract(ctx, amendment.contract_id, min_role)
    return amendment


@router.post("/contracts/{contract_id}/amendments", response_model=AmendmentOut, status_code=201)
def create_amendment(
    contract_id: uuid.UUID, body: AmendmentCreate, ctx: OrgContext = Depends(get_org_context)
) -> Amendment:
    """Record an amendment and apply its changes to the contract's current terms."""
    contract = _get_contract(ctx, contract_id, WorkspaceRole.EDITOR)
    amendment = Amendment(
        id=uuid.uuid4(),
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        contract_id=contract.id,
        title=body.title,
        effective_date=body.effective_date,
        signed_date=body.signed_date,
        description=body.description,
        created_by_id=ctx.user.id,
    )
    ctx.db.add(amendment)
    ctx.db.flush()
    try:
        apply_amendment(
            ctx.db,
            contract,
            amendment,
            body.contract.model_dump(exclude_unset=True),
            [c.model_dump(exclude_unset=True) for c in body.date_rules],
            [c.model_dump(exclude_unset=True) for c in body.payment_terms],
            [r.model_dump() for r in body.new_date_rules],
            [p.model_dump() for p in body.new_payment_terms],
            ctx.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="contract.amended",
        entity_type="contract",
        entity_id=contract.id,
        data=body.model_dump(mode="json", exclude_unset=True),
    )
    _recompute(ctx, contract)
    ctx.db.commit()
    ctx.db.refresh(amendment)
    return amendment


@router.patch("/amendments/{amendment_id}", response_model=AmendmentOut)
def update_amendment(
    amendment_id: uuid.UUID, body: AmendmentUpdate, ctx: OrgContext = Depends(get_org_context)
) -> Amendment:
    """Edit an amendment's details. To change what it changes, delete and record it again."""
    amendment = _get_amendment(ctx, amendment_id, WorkspaceRole.EDITOR)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(amendment, key, value)
    ctx.db.commit()
    ctx.db.refresh(amendment)
    return amendment


@router.delete("/amendments/{amendment_id}", response_model=AmendmentDeleted)
def delete_amendment(
    amendment_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> AmendmentDeleted:
    """Delete an amendment and undo its changes (except values changed again since)."""
    amendment = _get_amendment(ctx, amendment_id, WorkspaceRole.EDITOR)
    contract = amendment.contract
    total = len(amendment.changes)
    conflicts = revert_amendment(ctx.db, contract, amendment)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="contract.amendment_deleted",
        entity_type="contract",
        entity_id=contract.id,
        data={"title": amendment.title, "conflicts": conflicts},
    )
    keys = [d.storage_key for d in amendment.documents]
    ctx.db.delete(amendment)
    _recompute(ctx, contract)
    ctx.db.commit()
    storage = get_storage()
    for key in keys:
        storage.delete(key)
    return AmendmentDeleted(reverted=total - len(conflicts), conflicts=conflicts)


@router.post("/amendments/{amendment_id}/documents", response_model=AmendmentOut, status_code=201)
async def attach_amendment_document(
    amendment_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    ctx: OrgContext = Depends(get_org_context),
) -> Amendment:
    amendment = _get_amendment(ctx, amendment_id, WorkspaceRole.EDITOR)
    contract = amendment.contract
    data, filename, mime_type, sha256 = await _read_upload(file)
    _reject_duplicate(ctx, contract.workspace_id, sha256)
    document = _store_document(
        ctx, contract, data, filename, mime_type, sha256, amendment_id=amendment.id
    )
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=contract.workspace_id,
        actor_user_id=ctx.user.id,
        action="amendment.document_attached",
        entity_type="contract",
        entity_id=contract.id,
        data={"amendment": amendment.title, "filename": filename},
    )
    ctx.db.commit()
    ctx.db.refresh(amendment)
    enqueue_document(background, ctx.org_id, document.id)
    return amendment
