"""Agents HTTP API (tenant-scoped), gated by the subscription plan."""
from __future__ import annotations

from dataclasses import replace

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from app.core.crypto import decrypt, encrypt
from app.core.deps import (
    current_claims,
    authed_tenant,
    get_agents,
    get_subscriptions,
    require_role,
    resolve_tenant_worker,
    stored_credential,
)
from app.modules.audit import credentials as audit_credentials
from app.modules.audit import registry as audit_actions
from app.modules.agents.service import AGENT_TYPES, Agent, PlanLimitError
from app.modules.billing.plans import get_plan
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/agents", tags=["agents"])

# Config keys that must never round-trip to the client through the generic Agent views below --
# they're written via their own dedicated endpoints (e.g. vapi-credentials, which returns only a
# masked preview). Even though the vapi value is encrypted at rest, the general list/get/update
# endpoints returning the raw ciphertext blob is unnecessary exposure (OWASP sensitive data
# exposure): no legitimate client need ever reads it from here, and it shouldn't be handed out
# just because it happens to live in the same free-form config dict as everything else.
_REDACTED_CONFIG_KEYS = ("vapi_api_key_encrypted", "salesforce_client_secret_encrypted",
                         "calendly_token_encrypted", "clickup_api_token_encrypted",
                         "slack_bot_token_encrypted", "gmail_app_password_encrypted")


def _redact(agent: Agent) -> Agent:
    if not any(k in agent.config for k in _REDACTED_CONFIG_KEYS):
        return agent
    cfg = {k: v for k, v in agent.config.items() if k not in _REDACTED_CONFIG_KEYS}
    return replace(agent, config=cfg)


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
    sub = await run_in_threadpool(subs.status, tenant)
    plan = get_plan(sub.plan if sub and sub.status == "active" else "free")
    try:
        return await svc.create(tenant, body.name, plan, atype=body.atype)
    except PlanLimitError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


class AgentUsage(BaseModel):
    used_count: int
    worker_limit: int


@router.get("/usage", response_model=AgentUsage)
async def agent_usage(tenant: str = Depends(authed_tenant), svc=Depends(get_agents),
                      subs=Depends(get_subscriptions)) -> AgentUsage:
    sub = await run_in_threadpool(subs.status, tenant)
    plan = get_plan(sub.plan if sub and sub.status == "active" else "free")
    return AgentUsage(used_count=await svc.count(tenant), worker_limit=plan.worker_limit)


@router.get("")
async def list_agents(tenant: str = Depends(authed_tenant), svc=Depends(get_agents)) -> list[Agent]:
    # Hide archived agents (reversible soft-hide): config.archived is set via PUT /{id}/config
    # {"archived": true} and cleared with false. No hard delete -- the row and its data stay put,
    # so flipping the flag back restores the worker exactly as it was.
    return [_redact(a) for a in await svc.list(tenant)
            if a.enabled and a.config.get("archived") is not True]


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


def _plaintext_of_config(config: dict, key: str) -> str | None:
    """Decrypt a stored credential so the audit can fingerprint the value being replaced.

    Takes the config dict rather than the agent, because it is called with the snapshot the store
    captured under the row lock. The plaintext never leaves the audit helper.
    """
    stored = (config or {}).get(key)
    if not stored:
        return None
    try:
        return decrypt(stored)
    except Exception:  # noqa: BLE001 - a key rotation must not fail a credential write
        return None


@router.post("/{agent_id}/vapi-credentials")
async def save_vapi_credentials(agent_id: str, body: VapiCredentialsBody, request: Request,
                                claims: dict = Depends(current_claims), tenant: str = Depends(authed_tenant),
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
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_SET, provider="vapi", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=body.vapi_api_key,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "vapi_api_key_encrypted"), request=request))
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


# A tenant's Salesforce org is always reached on one of these Microsoft/Salesforce-owned host
# suffixes (My Domain / sandbox / Experience Cloud). Allow-listing them (not just requiring
# https://) stops the client-credentials token call in SalesforceClient from being pointed at
# internal infrastructure (SSRF -- OWASP A01 SSRF / API7), since that call ships the tenant's
# own client secret to whatever instance_url is stored here.
_SALESFORCE_HOST_SUFFIXES = (".salesforce.com", ".force.com", ".salesforce.mil")


class SalesforceCredentialsBody(BaseModel):
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    instance_url: str = Field(min_length=1, pattern=r"^https://")

    @field_validator("instance_url")
    @classmethod
    def _instance_url_is_salesforce(cls, v: str) -> str:
        host = (urlparse(v).hostname or "").lower()
        if not any(host == s.lstrip(".") or host.endswith(s) for s in _SALESFORCE_HOST_SUFFIXES):
            raise ValueError("instance_url must be a Salesforce host (*.salesforce.com / *.force.com)")
        return v


def _salesforce_view(agent: Agent) -> dict:
    cfg = agent.config
    return {
        "salesforce_credentials_added": bool(cfg.get("salesforce_credentials_added")),
        "instance_url": cfg.get("salesforce_instance_url") or "",
        "client_id_masked": _mask(cfg.get("salesforce_client_id") or ""),
    }


@router.post("/{agent_id}/salesforce-credentials")
async def save_salesforce_credentials(agent_id: str, body: SalesforceCredentialsBody, request: Request,
                                      claims: dict = Depends(current_claims),
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
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_SET, provider="salesforce", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=body.client_secret,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "salesforce_client_secret_encrypted"), request=request))
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
async def disconnect_salesforce(agent_id: str, request: Request,
                                claims: dict = Depends(current_claims),tenant: str = Depends(authed_tenant),
                                _role: dict = Depends(require_role(Role.editor)),
                                svc=Depends(get_agents)) -> dict:
    try:
        await svc.update_config(tenant, agent_id, {
            "salesforce_client_id": None, "salesforce_client_secret_encrypted": None,
            "salesforce_instance_url": None, "salesforce_credentials_added": False,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_REMOVED, provider="salesforce", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=None,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "salesforce_client_secret_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return {"disconnected": True}


@router.post("/{agent_id}/salesforce-credentials/test")
async def test_salesforce_credentials(agent_id: str, request: Request,
                                      claims: dict = Depends(current_claims),
                                      tenant: str = Depends(authed_tenant),
                                      _role: dict = Depends(require_role(Role.editor)),
                                      svc=Depends(get_agents)) -> dict:
    import asyncio

    from app.core.crypto import decrypt
    from app.integrations.clients import SalesforceAuthError, SalesforceClient

    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    await audit_credentials.record_credential_exercised(
        request.app.state.audit, provider="salesforce", tenant=tenant, agent_id=agent_id,
        claims=claims, request=request)
    cfg = agent.config
    if not cfg.get("salesforce_credentials_added"):
        raise HTTPException(status_code=422, detail="no Salesforce connection configured for this worker")
    client = SalesforceClient(client_id=cfg["salesforce_client_id"],
                              client_secret=decrypt(cfg["salesforce_client_secret_encrypted"]),
                              instance_url=cfg["salesforce_instance_url"])
    try:
        try:
            result = await asyncio.to_thread(client.test_connection)
        finally:
            await recheck()
        return result
    except SalesforceAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# --- Per-worker Calendly + ClickUp connections -------------------------------------------------
# Native V2 shape (same as Salesforce/Vapi above): each tenant supplies its OWN token, encrypted at
# rest and never returned in plaintext. Deliberately NOT a global Qiko-owned credential: a global
# token would push every customer's bookings/tasks into Qiko's own Calendly/ClickUp account.

class CalendlyCredentialsBody(BaseModel):
    # No max_length: a Field constraint failure puts the submitted value in the 422 body.
    token: str = Field(min_length=1)


def _calendly_view(agent: Agent) -> dict:
    cfg = agent.config
    return {
        "calendly_credentials_added": bool(cfg.get("calendly_credentials_added")),
        "calendly_event_type": cfg.get("calendly_event_type") or "",
        # The token IS the secret, so only its ciphertext is ever previewed (never _mask(decrypt(...))).
        "token_masked": _mask(cfg.get("calendly_token_encrypted") or ""),
    }


@router.post("/{agent_id}/calendly-credentials")
async def save_calendly_credentials(agent_id: str, body: CalendlyCredentialsBody, request: Request,
                                    claims: dict = Depends(current_claims),
                                    tenant: str = Depends(authed_tenant),
                                    _role: dict = Depends(require_role(Role.editor)),
                                    svc=Depends(get_agents)) -> dict:
    try:
        agent = await svc.update_config(tenant, agent_id, {
            "calendly_token_encrypted": encrypt(body.token),
            "calendly_credentials_added": True,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_SET, provider="calendly", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=body.token,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "calendly_token_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return _calendly_view(agent)


@router.get("/{agent_id}/calendly-credentials")
async def get_calendly_credentials(agent_id: str, tenant: str = Depends(authed_tenant),
                                   svc=Depends(get_agents)) -> dict:
    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _calendly_view(agent)


@router.delete("/{agent_id}/calendly-credentials")
async def disconnect_calendly(agent_id: str, request: Request,
                              claims: dict = Depends(current_claims),tenant: str = Depends(authed_tenant),
                              _role: dict = Depends(require_role(Role.editor)),
                              svc=Depends(get_agents)) -> dict:
    try:
        await svc.update_config(tenant, agent_id, {
            "calendly_token_encrypted": None, "calendly_credentials_added": False,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_REMOVED, provider="calendly", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=None,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "calendly_token_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return {"disconnected": True}


@router.post("/{agent_id}/calendly-credentials/test")
async def test_calendly_credentials(agent_id: str, request: Request,
                                    claims: dict = Depends(current_claims),
                                    tenant: str = Depends(authed_tenant),
                                    _role: dict = Depends(require_role(Role.editor)),
                                    svc=Depends(get_agents)) -> dict:
    import asyncio

    from app.integrations.clients import CalendlyAuthError, CalendlyClient

    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    await audit_credentials.record_credential_exercised(
        request.app.state.audit, provider="calendly", tenant=tenant, agent_id=agent_id,
        claims=claims, request=request)
    cfg = agent.config
    client = CalendlyClient(token=stored_credential(
        cfg, flag="calendly_credentials_added", key="calendly_token_encrypted", label="Calendly"))
    try:
        try:
            result = await asyncio.to_thread(client.test_connection)
        finally:
            await recheck()
        return result
    except CalendlyAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


class ClickUpCredentialsBody(BaseModel):
    api_token: str = Field(min_length=1)  # see CalendlyCredentialsBody: no max_length on secrets

    default_list_id: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")


def _clickup_view(agent: Agent) -> dict:
    cfg = agent.config
    return {
        "clickup_credentials_added": bool(cfg.get("clickup_credentials_added")),
        "default_list_id": cfg.get("clickup_default_list_id") or "",
        "token_masked": _mask(cfg.get("clickup_api_token_encrypted") or ""),
    }


@router.post("/{agent_id}/clickup-credentials")
async def save_clickup_credentials(agent_id: str, body: ClickUpCredentialsBody, request: Request,
                                   claims: dict = Depends(current_claims),
                                   tenant: str = Depends(authed_tenant),
                                   _role: dict = Depends(require_role(Role.editor)),
                                   svc=Depends(get_agents)) -> dict:
    try:
        agent = await svc.update_config(tenant, agent_id, {
            "clickup_api_token_encrypted": encrypt(body.api_token),
            "clickup_default_list_id": body.default_list_id or None,
            "clickup_credentials_added": True,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_SET, provider="clickup", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=body.api_token,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "clickup_api_token_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return _clickup_view(agent)


@router.get("/{agent_id}/clickup-credentials")
async def get_clickup_credentials(agent_id: str, tenant: str = Depends(authed_tenant),
                                  svc=Depends(get_agents)) -> dict:
    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _clickup_view(agent)


@router.delete("/{agent_id}/clickup-credentials")
async def disconnect_clickup(agent_id: str, request: Request,
                             claims: dict = Depends(current_claims),tenant: str = Depends(authed_tenant),
                             _role: dict = Depends(require_role(Role.editor)),
                             svc=Depends(get_agents)) -> dict:
    try:
        await svc.update_config(tenant, agent_id, {
            "clickup_api_token_encrypted": None, "clickup_default_list_id": None,
            "clickup_credentials_added": False,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_REMOVED, provider="clickup", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=None,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "clickup_api_token_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return {"disconnected": True}


@router.post("/{agent_id}/clickup-credentials/test")
async def test_clickup_credentials(agent_id: str, request: Request,
                                   claims: dict = Depends(current_claims),
                                   tenant: str = Depends(authed_tenant),
                                   _role: dict = Depends(require_role(Role.editor)),
                                   svc=Depends(get_agents)) -> dict:
    import asyncio

    from app.integrations.clients import ClickUpAuthError, ClickUpClient

    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    await audit_credentials.record_credential_exercised(
        request.app.state.audit, provider="clickup", tenant=tenant, agent_id=agent_id,
        claims=claims, request=request)
    cfg = agent.config
    client = ClickUpClient(api_token=stored_credential(
        cfg, flag="clickup_credentials_added", key="clickup_api_token_encrypted", label="ClickUp"))
    try:
        try:
            result = await asyncio.to_thread(client.test_connection)
        finally:
            await recheck()
        return result
    except ClickUpAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# --- Per-worker Slack + Gmail connections -------------------------------------------------------
# Same native shape: the tenant supplies its own Slack bot token / Gmail App Password. No Qiko-owned
# Slack app or Google Cloud project is required, and revoking the credential revokes our access.

class SlackCredentialsBody(BaseModel):
    bot_token: str = Field(min_length=1)  # no max_length: a 422 would echo the secret back
    default_channel: str = Field(default="", max_length=80)


def _slack_view(agent: Agent) -> dict:
    cfg = agent.config
    return {
        "slack_credentials_added": bool(cfg.get("slack_credentials_added")),
        "default_channel": cfg.get("slack_default_channel") or "",
        "token_masked": _mask(cfg.get("slack_bot_token_encrypted") or ""),
    }


@router.post("/{agent_id}/slack-credentials")
async def save_slack_credentials(agent_id: str, body: SlackCredentialsBody, request: Request,
                                 claims: dict = Depends(current_claims),
                                 tenant: str = Depends(authed_tenant),
                                 _role: dict = Depends(require_role(Role.editor)),
                                 svc=Depends(get_agents)) -> dict:
    try:
        agent = await svc.update_config(tenant, agent_id, {
            "slack_bot_token_encrypted": encrypt(body.bot_token),
            "slack_default_channel": body.default_channel or None,
            "slack_credentials_added": True,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_SET, provider="slack", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=body.bot_token,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "slack_bot_token_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return _slack_view(agent)


@router.get("/{agent_id}/slack-credentials")
async def get_slack_credentials(agent_id: str, tenant: str = Depends(authed_tenant),
                                svc=Depends(get_agents)) -> dict:
    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _slack_view(agent)


@router.delete("/{agent_id}/slack-credentials")
async def disconnect_slack(agent_id: str, request: Request,
                           claims: dict = Depends(current_claims),tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)),
                           svc=Depends(get_agents)) -> dict:
    try:
        await svc.update_config(tenant, agent_id, {
            "slack_bot_token_encrypted": None, "slack_default_channel": None,
            "slack_credentials_added": False,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_REMOVED, provider="slack", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=None,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "slack_bot_token_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return {"disconnected": True}


@router.post("/{agent_id}/slack-credentials/test")
async def test_slack_credentials(agent_id: str, request: Request,
                                 claims: dict = Depends(current_claims),
                                 tenant: str = Depends(authed_tenant),
                                 _role: dict = Depends(require_role(Role.editor)),
                                 svc=Depends(get_agents)) -> dict:
    import asyncio

    from app.integrations.clients import SlackAuthError, SlackClient

    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    await audit_credentials.record_credential_exercised(
        request.app.state.audit, provider="slack", tenant=tenant, agent_id=agent_id,
        claims=claims, request=request)
    client = SlackClient(bot_token=stored_credential(
        agent.config, flag="slack_credentials_added", key="slack_bot_token_encrypted", label="Slack"))
    try:
        try:
            result = await asyncio.to_thread(client.test_connection)
        finally:
            await recheck()
        return result
    except SlackAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


class GmailCredentialsBody(BaseModel):
    address: str = Field(min_length=3, max_length=320)
    app_password: str = Field(min_length=1)  # no max_length: a 422 would echo the secret back

    @field_validator("address")
    @classmethod
    def _looks_like_an_email(cls, v: str) -> str:
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("address must be an email address")
        return v


def _gmail_view(agent: Agent) -> dict:
    cfg = agent.config
    return {
        "gmail_credentials_added": bool(cfg.get("gmail_credentials_added")),
        "address": cfg.get("gmail_address") or "",
        "app_password_masked": _mask(cfg.get("gmail_app_password_encrypted") or ""),
    }


@router.post("/{agent_id}/gmail-credentials")
async def save_gmail_credentials(agent_id: str, body: GmailCredentialsBody, request: Request,
                                 claims: dict = Depends(current_claims),
                                 tenant: str = Depends(authed_tenant),
                                 _role: dict = Depends(require_role(Role.editor)),
                                 svc=Depends(get_agents)) -> dict:
    """Gmail sending via SMTP + an App Password (Google account -> Security -> App passwords)."""
    try:
        agent = await svc.update_config(tenant, agent_id, {
            "gmail_address": body.address,
            "gmail_app_password_encrypted": encrypt(body.app_password),
            "gmail_credentials_added": True,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_SET, provider="gmail", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=body.app_password,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "gmail_app_password_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return _gmail_view(agent)


@router.get("/{agent_id}/gmail-credentials")
async def get_gmail_credentials(agent_id: str, tenant: str = Depends(authed_tenant),
                                svc=Depends(get_agents)) -> dict:
    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _gmail_view(agent)


@router.delete("/{agent_id}/gmail-credentials")
async def disconnect_gmail(agent_id: str, request: Request,
                           claims: dict = Depends(current_claims),tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)),
                           svc=Depends(get_agents)) -> dict:
    try:
        await svc.update_config(tenant, agent_id, {
            "gmail_address": None, "gmail_app_password_encrypted": None,
            "gmail_credentials_added": False,
        }, audit=audit_credentials.credential_audit(
            action=audit_actions.CREDENTIAL_REMOVED, provider="gmail", tenant=tenant, agent_id=agent_id,
            agent_name=agent_id, claims=claims, secret=None,
            decrypt_previous=lambda cfg: _plaintext_of_config(cfg, "gmail_app_password_encrypted"), request=request))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="agent not found") from e
    return {"disconnected": True}


@router.post("/{agent_id}/gmail-credentials/test")
async def test_gmail_credentials(agent_id: str, request: Request,
                                 claims: dict = Depends(current_claims),
                                 tenant: str = Depends(authed_tenant),
                                 _role: dict = Depends(require_role(Role.editor)),
                                 svc=Depends(get_agents)) -> dict:
    import asyncio

    from app.integrations.clients import GmailSmtpClient, GmailSmtpError

    agent = await svc.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    await audit_credentials.record_credential_exercised(
        request.app.state.audit, provider="gmail", tenant=tenant, agent_id=agent_id,
        claims=claims, request=request)
    cfg = agent.config
    client = GmailSmtpClient(
        address=cfg.get("gmail_address") or "",
        app_password=stored_credential(cfg, flag="gmail_credentials_added",
                                       key="gmail_app_password_encrypted", label="Gmail"))
    try:
        try:
            result = await asyncio.to_thread(client.test_connection)
        finally:
            await recheck()
        return result
    except GmailSmtpError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
