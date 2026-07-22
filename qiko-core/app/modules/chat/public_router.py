"""Public (no-auth) chat for embedding. Answering stays agentic-first: it goes through the worker
-> agentcore (generator/critic/gate), never a direct model call. Only a 'ready' worker is served."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import build_tenant_worker
from app.modules.chat.public import AgentNotReadyError, public_ask

router = APIRouter(prefix="/public", tags=["public"])


class PublicChatBody(BaseModel):
    tenant: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    user_email: str = "guest@public"
    studio: dict | None = None


@router.post("/chat")
async def public_chat(body: PublicChatBody, request: Request) -> dict:
    settings = get_settings()
    if not settings.debug and not settings.public_chat_enabled:
        raise HTTPException(status_code=404, detail="not found")
    agent = await request.app.state.agents.get(body.tenant, body.worker_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="worker not found")
    worker = await build_tenant_worker(request, body.tenant, agent_id=body.worker_id)  # this worker's own config
    try:
        msg = await public_ask(worker, request.app.state.chat, agent_id=body.worker_id, user_email=body.user_email,
                               question=body.question, agent_ready=(agent.status == "ready"),
                               studio=body.studio)
    except AgentNotReadyError as e:
        raise HTTPException(status_code=403, detail="worker not ready") from e
    return {"role": msg.role, "text": msg.text}
