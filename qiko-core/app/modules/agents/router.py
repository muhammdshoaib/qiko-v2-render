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
_REDACTED_CONFIG_KEYS = ("vapi_api_key_encrypted", "salesforce_client_secret_encrypted")


def _redact(agent: Agent) -> Agent:
    if not any(k in agent.config for k in _REDACTED_CONFIG_KEYS):
        return agent
    cfg = {k: v for k, v in agent.config.items() if k not in _REDACTED_CONFIG_KEYS}
    return replace(agent, config=cfg)


# Known worker verticals. "worker" is the generic default; the others unlock a bespoke Studio
# cockpit (e.g. "sales_intelligence" -> tender ingestion + qualification + Salesforce push).
# Server-validated allowlist -- a client can't invent an arbitrary atype.
AGENT_TYPES = {"worker", "sales_intelligence"}


class CreateAgentBody(BaseModel):
    name: str = Field(min_length=1)
    atype: str = "worker"


@router.post("")
async def create_agent(body: CreateAgentBody, tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_agents),
                       subs=Depends(get_subscriptions)) -> Agent:
    # The plan is looked up server-side from the tenant's real subscription -- never trust a
    # client-supplied plan name here, or any tenant could self-upgrade past the free-tier limit.
    if body.atype not in AGENT_TYPES:
        raise HTTPException(status_code=422, detail="invalid atype")
    sub = subs.status(tenant)
    plan = get_plan(sub.plan if sub and sub.status == "active" else "free")
    try:
        return await svc.create(tenant, body.name, plan, atype=body.atype)
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


class SalesforceCredentialsBody(BaseModel):
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    instance_url: str = Field(min_length=1, pattern=r"^https://")


def _salesforce_view(agent: Agent) -> dict:
    cfg = agent.config
    return {
        "salesforce_credentials_added": bool(cfg.get("salesforce_credentials_added")),
        "instance_url": cfg.get("salesforce_instance_url") or "",
        "client_id_masked": _mask(cfg.get("salesforce_client_id") or ""),
    }


@router.post("/{agent_id}/salesforce-credentials")
async def save_salesforce_credentials(agent_id: str, body: SalesforceCredentialsBody,
                                      tenant: str = Depends(authed_tenant),
                                      _role: dict = Depends(require_role(Role.editor)),
                                      svc=Depends(get_agents)) -> dict:
    """Salesforce connection: client credentials grant against the tenant's own Connected App --
    see integrations/clients.py:SalesforceClient for why this shape (not a redirect OAuth flow)."""
    try:
        agent = await svc.update_config(tenant, agent_id, {
            "salesforce_client_id": body.client_id,
            "salesforce_client_secret_encrypted": encrypt(body.client_secret),
            "salesforce_instance_url": body.instance_url.rstrip("/"),
            "salesforce_credentials_added": True,
        })
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return _salesforce_view(agent)


@router.get("/{agent_id}/salesforce-credentials")
async def get_salesforce_credentials(agent_id: str, tenant: str = Depends(authed_tenant),
                                     svc=Depends(get_agents)) -> dict:
    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _salesforce_view(agent)


@router.delete("/{agent_id}/salesforce-credentials")
async def disconnect_salesforce(agent_id: str, tenant: str = Depends(authed_tenant),
                                _role: dict = Depends(require_role(Role.editor)),
                                svc=Depends(get_agents)) -> dict:
    try:
        await svc.update_config(tenant, agent_id, {
            "salesforce_client_id": None, "salesforce_client_secret_encrypted": None,
            "salesforce_instance_url": None, "salesforce_credentials_added": False,
        })
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return {"disconnected": True}


@router.post("/{agent_id}/salesforce-credentials/test")
async def test_salesforce_credentials(agent_id: str, tenant: str = Depends(authed_tenant),
                                      _role: dict = Depends(require_role(Role.editor)),
                                      svc=Depends(get_agents)) -> dict:
    import asyncio

    from app.core.crypto import decrypt
    from app.integrations.clients import SalesforceAuthError, SalesforceClient

    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    cfg = agent.config
    if not cfg.get("salesforce_credentials_added"):
        raise HTTPException(status_code=422, detail="no Salesforce connection configured for this worker")
    client = SalesforceClient(client_id=cfg["salesforce_client_id"],
                              client_secret=decrypt(cfg["salesforce_client_secret_encrypted"]),
                              instance_url=cfg["salesforce_instance_url"])
    try:
        return await asyncio.to_thread(client.test_connection)
    except SalesforceAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
