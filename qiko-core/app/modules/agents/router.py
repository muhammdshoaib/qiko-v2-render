"""Agents HTTP API (tenant-scoped), gated by the subscription plan."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_agents, get_subscriptions, require_role
from app.modules.agents.service import Agent, PlanLimitError
from app.modules.billing.plans import get_plan
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/agents", tags=["agents"])


class CreateAgentBody(BaseModel):
    name: str = Field(min_length=1)


@router.post("")
async def create_agent(body: CreateAgentBody, tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_agents),
                       subs=Depends(get_subscriptions)) -> Agent:
    # The plan is looked up server-side from the tenant's real subscription -- never trust a
    # client-supplied plan name here, or any tenant could self-upgrade past the free-tier limit.
    sub = subs.status(tenant)
    plan = get_plan(sub.plan if sub and sub.status == "active" else "free")
    try:
        return await svc.create(tenant, body.name, plan)
    except PlanLimitError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("")
async def list_agents(tenant: str = Depends(authed_tenant), svc=Depends(get_agents)) -> list[Agent]:
    return await svc.list(tenant)


@router.post("/{agent_id}/ready")
async def mark_ready(agent_id: str, tenant: str = Depends(authed_tenant),
                     _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_agents)) -> Agent:
    try:
        return await svc.mark_ready(tenant, agent_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
