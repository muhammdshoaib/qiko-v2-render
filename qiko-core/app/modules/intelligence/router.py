"""Per-agent Intelligence Worker HTTP API -- tenant-scoped catalog, connection verification
and grounded chat over captured signals.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_chat, require_role, resolve_tenant_worker
from app.modules.identity.rbac import Role
from app.modules.intelligence.catalog import SourceCatalog, UnknownSource
from app.modules.intelligence.chat import IntelligenceChat
from app.modules.chat.service import ChatService

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class VerifySourceBody(BaseModel):
    config: dict = Field(default_factory=dict)
    credential: str = Field(default="")


class AskBody(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: str = Field(default="")


def get_source_catalog(request: Request) -> SourceCatalog:
    return request.app.state.intelligence_catalog


async def _resolve_worker(request: Request, tenant: str, agent_id: str):
    """Confirm the agent belongs to the tenant and return the worker + post-call recheck hook."""
    worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    return worker, recheck


@router.get("/agents/{agent_id}/sources")
async def list_sources(agent_id: str, request: Request,
                       tenant: str = Depends(authed_tenant),
                       catalog: SourceCatalog = Depends(get_source_catalog)) -> list[dict]:
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    await recheck()
    return catalog.items(connected=set())


@router.get("/agents/{agent_id}/sources/{key}")
async def get_source(agent_id: str, key: str, request: Request,
                     tenant: str = Depends(authed_tenant),
                     catalog: SourceCatalog = Depends(get_source_catalog)) -> dict:
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    await recheck()
    definition = catalog.definition(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="source not found")
    return {
        "key": definition.key,
        "name": definition.name,
        "description": definition.description,
        "pollable": definition.pollable,
        "connected": False,
    }


@router.post("/agents/{agent_id}/sources/{key}/verify")
async def verify_source(agent_id: str, key: str, body: VerifySourceBody, request: Request,
                        tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        catalog: SourceCatalog = Depends(get_source_catalog)) -> dict:
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    try:
        connector = catalog.connector_for(key)
    except UnknownSource as e:
        raise HTTPException(status_code=404, detail="source not found") from e
    result = await connector.verify(config=body.config, credential=body.credential)
    await recheck()
    return result


@router.post("/agents/{agent_id}/chat/ask")
async def ask(
    agent_id: str, body: AskBody, request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
    chat: ChatService = Depends(get_chat),
) -> dict:
    """Ask the intelligence worker a question grounded in its captured signals."""
    user_id = claims.get("sub", "public")
    worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    intelligence = IntelligenceChat(worker)
    try:
        result = await intelligence.answer(
            body.question, conversation_id=body.conversation_id or None,
            chat=chat, user_id=user_id)
    finally:
        await recheck()
    return result


@router.get("/agents/{agent_id}/chat/{conversation_id}/history")
async def chat_history(
    agent_id: str, conversation_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.viewer)),
    chat: ChatService = Depends(get_chat),
) -> list[dict]:
    """Recent messages for one intelligence conversation, oldest first."""
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    try:
        messages = await chat.history(tenant, conversation_id)
    finally:
        await recheck()
    return [{"role": m.role, "text": m.text, "created_at": m.created_at} for m in messages]


@router.get("/agents/{agent_id}/conversations")
async def list_conversations(
    agent_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.viewer)),
    chat: ChatService = Depends(get_chat),
) -> list[dict]:
    """All conversations for this worker that the tenant can see."""
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    try:
        conversations = await chat.list_for_agent(tenant, agent_id)
    finally:
        await recheck()
    return [{"id": c.id, "user_id": c.user_id, "agent_id": c.agent_id,
             "crm_eligible": c.crm_eligible, "created_at": c.created_at} for c in conversations]
