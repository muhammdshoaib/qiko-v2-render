"""Public (no-auth) chat for embedding. Answering stays agentic-first: it goes through the worker
-> agentcore (generator/critic/gate), never a direct model call. Only a 'ready' worker is served."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.deps import require_available_worker, resolve_tenant_worker
from app.modules.chat.public import AgentNotReadyError, public_ask

router = APIRouter(prefix="/public", tags=["public"])


class PublicChatBody(BaseModel):
    # tenant is optional: a public "/chat/{workerId}" link only carries the (globally unique) worker
    # id, so the tenant is resolved server-side from it (mirrors V1 /avatar/public/{agentId}/chat).
    tenant: str | None = Field(default=None, max_length=128)
    worker_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=4000)
    user_email: str = Field(default="guest@public", max_length=320)
    studio: dict | None = None

    @field_validator("studio")
    @classmethod
    def validate_studio(cls, studio: dict | None) -> dict | None:
        if studio is None:
            return None
        allowed = {"summary", "schema", "fileList", "userNamespaces"}
        if set(studio) - allowed or len(str(studio)) > 20_000:
            raise ValueError("studio context exceeds the allowed shape or size")
        return studio


def _public_enabled() -> None:
    settings = get_settings()
    if not settings.debug and not settings.public_chat_enabled:
        raise HTTPException(status_code=404, detail="not found")


async def _resolve_public_tenant(request: Request, worker_id: str, tenant: str | None) -> str:
    """Resolve the tenant for a public worker id. A public link carries only the worker id, so we
    look the agent up globally; the ready-gate is still enforced by the caller. A supplied tenant is
    honoured (embed links) but must match the worker's real tenant."""
    agent = await request.app.state.agents.get_by_id(worker_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="worker not found")
    if tenant and tenant != agent.tenant:
        raise HTTPException(status_code=404, detail="worker not found")
    return agent.tenant


@router.get("/worker/{worker_id}")
async def public_worker(worker_id: str, request: Request) -> dict:
    """Public worker detail for the guest chat page: name + type for branding. Only a READY worker is
    exposed (mirrors V1 getAgent: not-ready/invalid -> 403/404, no private fields)."""
    _public_enabled()
    agent = await request.app.state.agents.get_by_id(worker_id)
    if agent is None or not agent.enabled:
        raise HTTPException(status_code=404, detail="worker not found")
    if agent.status != "ready":
        raise HTTPException(status_code=403, detail="worker is not available for public chat")
    return {"id": agent.id, "name": agent.name, "atype": agent.atype}


@router.post("/chat")
async def public_chat(body: PublicChatBody, request: Request) -> dict:
    _public_enabled()
    tenant = await _resolve_public_tenant(request, body.worker_id, body.tenant)

    async def recheck_public_worker() -> None:
        agent = await require_available_worker(
            agents=request.app.state.agents,
            tenant=tenant,
            agent_id=body.worker_id,
        )
        if agent.status != "ready":
            raise AgentNotReadyError("agent is not ready for public chat")

    try:
        await recheck_public_worker()
        worker, _recheck = await resolve_tenant_worker(request, tenant, body.worker_id)
        msg = await public_ask(
            worker, request.app.state.chat, agent_id=body.worker_id,
            user_email=body.user_email, question=body.question,
            recheck_worker=recheck_public_worker, studio=body.studio)
        await recheck_public_worker()
    except AgentNotReadyError as exc:
        raise HTTPException(status_code=403, detail="worker not ready") from exc
    return {"role": msg.role, "text": msg.text}
