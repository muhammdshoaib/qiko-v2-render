"""Chat HTTP API (tenant-scoped, agentic-first)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.core.deps import current_claims, authed_tenant, get_chat, get_file_generator, resolve_tenant_worker

router = APIRouter(prefix="/chat", tags=["chat"])


class AskBody(BaseModel):
    conversation_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    topic: str | None = None
    agent_id: str = Field(min_length=1)


@router.post("/ask")
async def ask(body: AskBody, request: Request, tenant: str = Depends(authed_tenant), chat=Depends(get_chat)) -> dict:
    worker, recheck = await resolve_tenant_worker(request, tenant, body.agent_id)
    msg = await chat.ask(
        worker, body.conversation_id, body.question, topic=body.topic,
        agent_id=body.agent_id, recheck_worker=recheck)
    await recheck()
    return {"role": msg.role, "text": msg.text}


@router.get("/history/{conversation_id}")
async def history(conversation_id: str, tenant: str = Depends(authed_tenant), chat=Depends(get_chat)) -> list[dict]:
    return [{"role": m.role, "text": m.text} for m in await chat.history(tenant, conversation_id)]


@router.delete("/history/{conversation_id}")
async def clear_history(conversation_id: str, request: Request,
                        claims: dict = Depends(current_claims),
                        tenant: str = Depends(authed_tenant), chat=Depends(get_chat)) -> dict:
    """Delete every message in a conversation.

    Reachable by ANY authenticated role including viewer, with no confirmation, and it destroys content
    the product itself treats as the record. Recording the message count before the wipe is the only
    way the trail can distinguish clearing an empty test thread from destroying a year of a customer's
    support history.
    """
    # The count comes from the delete itself. Reading history() to count first was wrong twice: it
    # defaults to a 20-message window, so the number saturated at 20 and could never distinguish an
    # empty test thread from a year of support history, and the SQL store has no LIMIT so it
    # materialised every message body to produce a number it then capped.
    removed = await chat.clear(tenant, conversation_id)
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.CHAT_HISTORY_DELETED, target_id=conversation_id, tenant_id=tenant,
        actor_type=audit.USER, actor_id=str(claims.get("sub") or ""),
        actor_label=str(claims.get("email") or ""),
        changes=audit.diff(audit_actions.CHAT_HISTORY_DELETED, {},
                           {"messages_removed": removed})), request=request)
    return {"cleared": True}


class ConversationBody(BaseModel):
    user_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)


@router.post("/conversations")
async def create_conversation(body: ConversationBody, request: Request,
                              tenant: str = Depends(authed_tenant), chat=Depends(get_chat)) -> dict:
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.agent_id)
    await recheck()
    conversation_id = await chat.find_or_create(
        tenant, body.user_id, body.agent_id, recheck_worker=recheck)
    await recheck()
    return {"conversation_id": conversation_id}


class FileSpec(BaseModel):
    title: str = ""
    paragraphs: list[str] = []
    rows: list[list[str | int | float]] = []
    headers: list[str] = []


class FileBody(BaseModel):
    fmt: str = Field(pattern="^(csv|xlsx|docx|pdf)$")
    filename: str = Field(min_length=1)
    # Typed on purpose: an untyped dict let {"paragraphs": [1]} or {"paragraphs": 5} reach the
    # generator and raise TypeError -> unhandled 500. Now malformed input is a clean 422.
    spec: FileSpec


@router.post("/files")
def generate_file(body: FileBody, tenant: str = Depends(authed_tenant), gen=Depends(get_file_generator)) -> dict:
    return {"key": gen.generate(tenant, body.fmt, body.filename, body.spec.model_dump())}


@router.get("/files/{key:path}")
def download_file(key: str, tenant: str = Depends(authed_tenant), gen=Depends(get_file_generator)) -> Response:
    try:
        data = gen.storage.get(tenant, key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="file not found") from e
    return Response(content=data, media_type="application/octet-stream")
