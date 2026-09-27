"""QIKO-1073: read-only platform-admin support view of one intelligence worker's own chat and
discrepancies. No route here accepts a body or mutates anything.

Every route resolves its tenant from the agent row itself (AgentService.get_by_id, the existing
cross-tenant-by-id exception already used for public chat), never from a caller-supplied tenant
or the admin's own claims - the BOLA guard for this feature is "you can only look up a worker you
already know the id of, and a conversation that actually belongs to it", not "you can name any
tenant" and not "any conversation id in the same tenant is fair game once you know one worker id".
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import current_claims, get_agents, get_chat, require_platform_capability
from app.modules.agents.service import Agent, AgentService
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.chat.service import ChatService
from app.modules.identity.admin_rbac import Capability
from app.modules.intelligence.discrepancies import DiscrepancyEngine

router = APIRouter(prefix="/admin/support", tags=["admin-support"])

SUPPORTED_ATYPE = "intelligence"


class SupportWorkerSummaryOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    atype: str


class SupportConversationOut(BaseModel):
    id: str
    user_id: str
    # ConversationSummary.created_at is "datetime | None" (SQL-backed stores populate it,
    # in-memory does not need to) - Optional here for the same reason.
    created_at: datetime | None


class SupportMessageOut(BaseModel):
    role: str
    text: str
    # Message.created_at is "datetime | None" for the same reason as above.
    created_at: datetime | None


class SupportDiscrepancySourceOut(BaseModel):
    source: str
    source_label: str
    external_id: str
    url: str | None
    actor: str
    occurred_at: str | None


class SupportDiscrepancyOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # "class" is a Python reserved word, so Discrepancy.to_dict()'s literal "class" key needs an
    # aliased field name here rather than being usable directly.
    class_: str = Field(alias="class")
    class_label: str
    severity: str
    ref: str | None
    project_key: str | None
    title: str
    summary: str
    claimed_at: str | None
    evidence_at: str | None
    occurred_at: str | None
    sources: list[SupportDiscrepancySourceOut]


class SupportDiscrepancyProjectOut(BaseModel):
    key: str
    count: int


class SupportDiscrepanciesOut(BaseModel):
    items: list[SupportDiscrepancyOut]
    total: int
    projects: list[SupportDiscrepancyProjectOut]


async def _resolve_intelligence_worker(agents: AgentService, agent_id: str) -> Agent:
    agent = await agents.get_by_id(agent_id)
    if agent is None or agent.atype != SUPPORTED_ATYPE:
        raise HTTPException(status_code=404, detail="worker not found")
    return agent


async def _verify_conversation_belongs_to_agent(
    chat: ChatService, agent: Agent, conversation_id: str,
) -> None:
    """ChatService.history(tenant, conversation_id) takes no agent_id, so on its own it can only
    confirm a conversation belongs to the TENANT, not to the resolved worker. Without this check, a
    caller holding the capability for worker A could pass any conversation_id that exists in the
    same tenant - including one that belongs to a different worker - and read its messages. That
    would defeat the point of scoping this feature to one agent_id, even though it never crosses
    the tenant boundary. 404, not 403, to match _resolve_intelligence_worker's convention of not
    confirming or denying existence to a caller who does not already hold the id.
    """
    conversations = await chat.list_for_agent(agent.tenant, agent.id)
    if not any(c.id == conversation_id for c in conversations):
        raise HTTPException(status_code=404, detail="conversation not found")


async def _audit(request: Request, claims: dict, agent: Agent, view: str) -> None:
    # Matches the existing platform-admin audit call pattern exactly (see STUDIO_TOGGLED /
    # CUSTOMER_SOFT_DELETED in app/modules/admin/router.py): tenant_id is the tenant the event is
    # ABOUT, not the actor's own (the actor is a platform admin, who has none). `metadata` is not
    # allowlist-restricted like `changes`/diff_fields is, so the sub-view name is safe to pass
    # directly; it must never carry the conversation/discrepancy content itself.
    email = str(claims.get("email") or "")
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.SUPPORT_WORKER_VIEWED,
        target_id=agent.id, target_label=agent.name, tenant_id=agent.tenant,
        actor_type=audit.PLATFORM_ADMIN, actor_id=email, actor_label=email,
        metadata={"view": view},
    ), request=request)


@router.get("/workers/{agent_id}", response_model=SupportWorkerSummaryOut)
async def worker_summary(
    agent_id: str, request: Request,
    claims: dict = Depends(current_claims),
    _identity=Depends(require_platform_capability(Capability.support_view_worker)),
    agents: AgentService = Depends(get_agents),
) -> dict:
    agent = await _resolve_intelligence_worker(agents, agent_id)
    await _audit(request, claims, agent, "summary")
    return {"id": agent.id, "tenant_id": agent.tenant, "name": agent.name, "atype": agent.atype}


@router.get("/workers/{agent_id}/conversations", response_model=list[SupportConversationOut])
async def worker_conversations(
    agent_id: str, request: Request,
    claims: dict = Depends(current_claims),
    _identity=Depends(require_platform_capability(Capability.support_view_worker)),
    agents: AgentService = Depends(get_agents),
    chat: ChatService = Depends(get_chat),
) -> list[dict]:
    agent = await _resolve_intelligence_worker(agents, agent_id)
    conversations = await chat.list_for_agent(agent.tenant, agent_id)
    await _audit(request, claims, agent, "conversations")
    return [{"id": c.id, "user_id": c.user_id, "created_at": c.created_at} for c in conversations]


@router.get("/workers/{agent_id}/conversations/{conversation_id}",
           response_model=list[SupportMessageOut])
async def worker_conversation_history(
    agent_id: str, conversation_id: str, request: Request,
    claims: dict = Depends(current_claims),
    _identity=Depends(require_platform_capability(Capability.support_view_worker)),
    agents: AgentService = Depends(get_agents),
    chat: ChatService = Depends(get_chat),
) -> list[dict]:
    agent = await _resolve_intelligence_worker(agents, agent_id)
    await _verify_conversation_belongs_to_agent(chat, agent, conversation_id)
    messages = await chat.history(agent.tenant, conversation_id)
    await _audit(request, claims, agent, "conversation_history")
    return [{"role": m.role, "text": m.text, "created_at": m.created_at} for m in messages]


@router.get("/workers/{agent_id}/discrepancies", response_model=SupportDiscrepanciesOut)
async def worker_discrepancies(
    agent_id: str, request: Request,
    claims: dict = Depends(current_claims),
    _identity=Depends(require_platform_capability(Capability.support_view_worker)),
    agents: AgentService = Depends(get_agents),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    agent = await _resolve_intelligence_worker(agents, agent_id)
    engine = DiscrepancyEngine(request.app.state.intelligence_signal_store)
    discrepancies, total, counts = await engine.analyze_paginated(
        agent.tenant, agent_id, limit=limit, offset=offset)
    await _audit(request, claims, agent, "discrepancies")
    return {
        "items": [d.to_dict() for d in discrepancies],
        "total": total,
        "projects": [{"key": key, "count": count} for key, count in counts.items()],
    }
