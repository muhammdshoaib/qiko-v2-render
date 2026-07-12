"""Agents HTTP API (tenant-scoped), gated by the subscription plan."""
from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.crypto import encrypt
from app.core.deps import authed_tenant, get_agents, get_subscriptions, require_role
from app.modules.agents.service import Agent, PlanLimitError
from app.modules.billing.plans import get_plan
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/agents", tags=["agents"])

# Config keys that must never round-trip to the client through the generic Agent views below --
# they're written via their own dedicated endpoints (e.g. vapi-credentials, which returns only a
# masked preview). Even though the vapi value is encrypted at rest, the general list/get/update
# endpoints returning the raw ciphertext blob is unnecessary exposure (OWASP sensitive data
# exposure): no legitimate client need ever reads it from here, and it shouldn't be handed out
# just because it happens to live in the same free-form config dict as everything else.
_REDACTED_CONFIG_KEYS = ("vapi_api_key_encrypted",)


def _redact(agent: Agent) -> Agent:
    if not any(k in agent.config for k in _REDACTED_CONFIG_KEYS):
        return agent
    cfg = {k: v for k, v in agent.config.items() if k not in _REDACTED_CONFIG_KEYS}
    return replace(agent, config=cfg)


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
    return [_redact(a) for a in await svc.list(tenant)]


class UpdateConfigBody(BaseModel):
    patch: dict = Field(default_factory=dict)


@router.put("/{agent_id}/config")
async def update_config(agent_id: str, body: UpdateConfigBody, tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_agents)) -> Agent:
    """Merge-patch the worker's free-form config -- backs the Train wizard's Background/Tone steps."""
    try:
        return _redact(await svc.update_config(tenant, agent_id, body.patch))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e


@router.post("/{agent_id}/ready")
async def mark_ready(agent_id: str, tenant: str = Depends(authed_tenant),
                     _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_agents)) -> Agent:
    try:
        return _redact(await svc.mark_ready(tenant, agent_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e


class VapiCredentialsBody(BaseModel):
    vapi_assistant_id: str = Field(min_length=1)
    vapi_public_key: str = Field(min_length=1)
    vapi_api_key: str = Field(min_length=1)


def _mask(secret: str) -> str:
    return f"{secret[:4]}{'*' * max(len(secret) - 4, 4)}" if secret else ""


@router.post("/{agent_id}/vapi-credentials")
async def save_vapi_credentials(agent_id: str, body: VapiCredentialsBody, tenant: str = Depends(authed_tenant),
                                _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_agents)) -> dict:
    """Voice connection (Vapi.ai). The secret key is encrypted at rest and never returned in
    plaintext again -- only a masked preview, unlike the Laravel VapiCredentialsController this
    replaces, which returned the raw ciphertext for client-side decryption (a real anti-pattern)."""
    try:
        agent = await svc.update_config(tenant, agent_id, {
            "vapi_assistant_id": body.vapi_assistant_id,
            "vapi_public_key": body.vapi_public_key,
            "vapi_api_key_encrypted": encrypt(body.vapi_api_key),
            "vapi_credentials_added": True,
        })
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return _vapi_view(agent)


@router.get("/{agent_id}/vapi-credentials")
async def get_vapi_credentials(agent_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_agents)) -> dict:
    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _vapi_view(agent)


def _vapi_view(agent: Agent) -> dict:
    cfg = agent.config
    return {
        "vapi_credentials_added": bool(cfg.get("vapi_credentials_added")),
        "vapi_assistant_id": cfg.get("vapi_assistant_id", ""),
        "vapi_public_key": cfg.get("vapi_public_key", ""),
        "vapi_api_key_masked": _mask(cfg.get("vapi_api_key_encrypted", "")),
    }


class CalendlyEventTypeBody(BaseModel):
    calendly_event_type: str = Field(min_length=1)


@router.put("/{agent_id}/calendly-event-type")
async def update_calendly_event_type(agent_id: str, body: CalendlyEventTypeBody,
                                     tenant: str = Depends(authed_tenant),
                                     _role: dict = Depends(require_role(Role.editor)),
                                     svc=Depends(get_agents)) -> Agent:
    try:
        return _redact(await svc.update_config(tenant, agent_id, {
            "calendly_event_type": body.calendly_event_type, "calendly_is_linked": True,
        }))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
