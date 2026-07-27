"""Chat HTTP API (tenant-scoped, agentic-first)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_chat, get_file_generator, resolve_tenant_worker

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
async def clear_history(conversation_id: str, tenant: str = Depends(authed_tenant), chat=Depends(get_chat)) -> dict:
    await chat.clear(tenant, conversation_id)
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


class FileBody(BaseModel):
    fmt: str = Field(pattern="^(csv|xlsx|docx|pdf)$")
    filename: str = Field(min_length=1)
    spec: dict


@router.post("/files")
def generate_file(body: FileBody, tenant: str = Depends(authed_tenant), gen=Depends(get_file_generator)) -> dict:
    return {"key": gen.generate(tenant, body.fmt, body.filename, body.spec)}


@router.get("/files/{key:path}")
def download_file(key: str, tenant: str = Depends(authed_tenant), gen=Depends(get_file_generator)) -> Response:
    try:
        data = gen.storage.get(tenant, key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="file not found") from e
    return Response(content=data, media_type="application/octet-stream")
