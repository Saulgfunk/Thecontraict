import json
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import chat
from app.db import SessionLocal, set_tenant
from app.deps import OrgContext, get_org_context
from app.models import ChatMessage, ChatThread, Contract, ContractStatus

router = APIRouter(prefix="/organizations/{org_id}/chat", tags=["chat"])
log = logging.getLogger(__name__)


class ThreadCreate(BaseModel):
    workspace_id: uuid.UUID
    contract_id: uuid.UUID | None = None


class ThreadOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    contract_id: uuid.UUID | None
    title: str
    created_at: datetime
    updated_at: datetime


class Citation(BaseModel):
    contract_id: uuid.UUID
    contract_title: str
    clause_refs: list[str]
    cited_text: str


class MessageBlock(BaseModel):
    text: str
    citations: list[Citation] = []


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    blocks: list[MessageBlock]
    error: str | None
    created_at: datetime


class ThreadDetail(ThreadOut):
    messages: list[MessageOut]


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _thread_out(t: ChatThread) -> ThreadOut:
    return ThreadOut.model_validate(t, from_attributes=True)


def _message_out(m: ChatMessage) -> MessageOut:
    return MessageOut.model_validate(m, from_attributes=True)


def _get_thread(ctx: OrgContext, thread_id: uuid.UUID) -> ChatThread:
    thread = ctx.db.get(ChatThread, thread_id)
    # Threads are private to their author, and require continued workspace access.
    if thread is None or thread.organization_id != ctx.org_id or thread.user_id != ctx.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    try:
        ctx.get_workspace(thread.workspace_id)
    except HTTPException as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found") from exc
    return thread


@router.post("/threads", response_model=ThreadOut, status_code=201)
def create_thread(body: ThreadCreate, ctx: OrgContext = Depends(get_org_context)) -> ThreadOut:
    workspace = ctx.get_workspace(body.workspace_id)
    title = f"Questions about {workspace.name}"
    if body.contract_id:
        contract = ctx.db.get(Contract, body.contract_id)
        if contract is None or contract.workspace_id != workspace.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
        title = f"Questions about {contract.title}"
    thread = ChatThread(
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        contract_id=body.contract_id,
        user_id=ctx.user.id,
        title=title[:300],
    )
    ctx.db.add(thread)
    ctx.db.commit()
    return _thread_out(thread)


@router.get("/threads", response_model=list[ThreadOut])
def list_threads(
    ctx: OrgContext = Depends(get_org_context),
    workspace_id: uuid.UUID | None = None,
    contract_id: uuid.UUID | None = None,
) -> list[ThreadOut]:
    query = (
        select(ChatThread)
        .where(ChatThread.organization_id == ctx.org_id, ChatThread.user_id == ctx.user.id)
        .order_by(ChatThread.updated_at.desc())
        .limit(50)
    )
    if workspace_id:
        ctx.get_workspace(workspace_id)
        query = query.where(ChatThread.workspace_id == workspace_id)
    if contract_id:
        query = query.where(ChatThread.contract_id == contract_id)
    threads = [t for t in ctx.db.scalars(query) if ctx.workspace_role(t.workspace_id)]
    return [_thread_out(t) for t in threads]


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
def get_thread(thread_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)) -> ThreadDetail:
    thread = _get_thread(ctx, thread_id)
    return ThreadDetail(
        **_thread_out(thread).model_dump(), messages=[_message_out(m) for m in thread.messages]
    )


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)) -> None:
    ctx.db.delete(_get_thread(ctx, thread_id))
    ctx.db.commit()


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.post(
    "/threads/{thread_id}/messages",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def send_message(
    thread_id: uuid.UUID, body: MessageCreate, ctx: OrgContext = Depends(get_org_context)
) -> StreamingResponse:
    """Ask a question. Streams Server-Sent Events: ``{"type": "delta", "text"}`` while the
    answer is written, then ``{"type": "message", "message"}`` with citations, or
    ``{"type": "error", "detail"}``."""
    thread = _get_thread(ctx, thread_id)
    previous = list(thread.messages)

    if thread.contract_id:
        contracts = [c for c in [ctx.db.get(Contract, thread.contract_id)] if c is not None]
    else:
        contracts = list(
            ctx.db.scalars(
                select(Contract)
                .where(
                    Contract.workspace_id == thread.workspace_id,
                    Contract.status != ContractStatus.PROCESSING,
                )
                .order_by(Contract.title)
            )
        )
    sources = chat.build_sources(ctx.db, contracts, body.text, single=bool(thread.contract_id))
    titles = {c.id: c.title for c in contracts}

    user_message = ChatMessage(
        organization_id=ctx.org_id,
        thread_id=thread.id,
        role="user",
        blocks=[{"text": body.text}],
    )
    ctx.db.add(user_message)
    if not previous:
        thread.title = body.text[:120]
    thread.updated_at = datetime.now(UTC)
    ctx.db.commit()

    if sources:
        content: list[dict[str, Any]] = [s.to_param() for s in sources]
        content.append({"type": "text", "text": body.text})
    else:
        content = [
            {
                "type": "text",
                "text": "(No analysed contracts are available in this workspace yet.)\n\n"
                + body.text,
            }
        ]
    messages = [*chat.history_params(previous), {"role": "user", "content": content}]
    org_id, thread_db_id = ctx.org_id, thread.id

    def save(
        blocks: list[dict[str, Any]], result: chat.ChatResult | None, error: str | None
    ) -> MessageOut:
        with SessionLocal() as db:
            set_tenant(db, org_id)
            message = ChatMessage(
                organization_id=org_id,
                thread_id=thread_db_id,
                role="assistant",
                blocks=blocks,
                model=result.model if result else None,
                input_tokens=result.input_tokens if result else None,
                output_tokens=result.output_tokens if result else None,
                error=error,
            )
            db.add(message)
            db.commit()
            db.refresh(message)
            return _message_out(message)

    def events() -> Iterator[str]:
        written = ""
        try:
            model = chat.get_chat_model()
            for item in model.stream(chat.SYSTEM_PROMPT, messages):
                if isinstance(item, str):
                    written += item
                    yield _sse({"type": "delta", "text": item})
                    continue
                blocks = [
                    {
                        "text": b["text"],
                        "citations": chat.resolve_citations(
                            b.get("citations", []), sources, titles
                        ),
                    }
                    for b in item.blocks
                ]
                yield _sse(
                    {"type": "message", "message": save(blocks, item, None).model_dump(mode="json")}
                )
                return
            raise chat.ChatError("The answer ended unexpectedly")
        except Exception as exc:
            log.exception("Chat failed")
            detail = str(exc) if isinstance(exc, chat.ChatError) else "The AI service failed"
            saved = save([{"text": written}] if written else [], None, detail)
            yield _sse(
                {"type": "error", "detail": detail, "message": saved.model_dump(mode="json")}
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
