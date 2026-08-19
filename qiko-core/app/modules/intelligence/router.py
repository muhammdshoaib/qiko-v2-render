"""Per-agent Intelligence Worker HTTP API -- tenant-scoped catalog, connection verification
and grounded chat over captured signals.
"""
from __future__ import annotations

import logging

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.deps import (
    authed_tenant, current_claims, get_agents, get_chat, get_slack_oauth,
    require_role, resolve_tenant_worker, stored_credential,
)
from app.modules.audit import credentials as audit_credentials
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.agents.service import AgentService
from app.modules.identity.rbac import Role
from app.modules.intelligence.catalog import SourceCatalog, UnknownSource
from app.modules.intelligence.chat import IntelligenceChat
from app.modules.intelligence.discrepancies import DiscrepancyEngine
from app.modules.intelligence.ingest import ingest_source
from app.modules.chat.service import ChatService

router = APIRouter(prefix="/intelligence", tags=["intelligence"])
logger = logging.getLogger(__name__)


class VerifySourceBody(BaseModel):
    config: dict = Field(default_factory=dict)
    credential: str = Field(default="")


class AskBody(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: str = Field(default="")


class ConnectSourceBody(BaseModel):
    """Request body for source connections. Fields are optional because each source uses a subset."""
    model_config = ConfigDict(extra="forbid")

    token: str = Field(default="")
    repo_allowlist: list[str] = Field(default_factory=list)
    watched_branches: list[str] = Field(default_factory=list)
    project_keys: list[str] = Field(default_factory=list)
    project_key: str = Field(default="")
    base_url: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _normalize_project_keys(cls, values):
        if isinstance(values, dict) and values.get("project_key") and not values.get("project_keys"):
            values["project_keys"] = [values["project_key"]]
        return values


class SlackWatchChannelsBody(BaseModel):
    channel_ids: list[str] = Field(default_factory=list)


# Config keys managed by the source-connection endpoints. They are encrypted at rest, returned only
# as masked previews, and refused by the generic PUT /agents/{id}/config merge-patch.
_SOURCE_CONFIG = {
    "github": {
        "added": "github_credentials_added",
        "token": "github_token_encrypted",
        "allowlist": "github_repo_allowlist",
        "watched_branches": "github_watched_branches",
        "label": "GitHub",
    },
    "qiko_track": {
        "added": "qiko_track_credentials_added",
        "token": "qiko_track_token_encrypted",
        "project_keys": "qiko_track_project_keys",
        "base_url": "qiko_track_base_url",
        "label": "Qiko Track",
    },
    "slack": {
        "watched": "slack_watched_channels",
        "team_id": "slack_team_id",
    },
}


def _mask(secret: str) -> str:
    return f"{secret[:4]}{'*' * max(len(secret) - 4, 4)}" if secret else ""


def _plaintext_of_config(config: dict, key: str) -> str | None:
    """Decrypt a stored credential from an agent config snapshot."""
    stored = (config or {}).get(key)
    if not stored:
        return None
    try:
        return decrypt(stored)
    except Exception:  # noqa: BLE001 - a key rotation must not fail a credential write
        return None


def get_source_catalog(request: Request) -> SourceCatalog:
    return request.app.state.intelligence_catalog


async def _resolve_worker(request: Request, tenant: str, agent_id: str):
    """Confirm the agent belongs to the tenant and return the worker + post-call recheck hook."""
    worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    return worker, recheck


async def _agent_or_404(agents: AgentService, tenant: str, agent_id: str) -> None:
    if await agents.get(tenant, agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")


def _build_credential_audit(*, provider: str, secret: str | None, encrypted_key: str,
                            tenant: str, agent_id: str, agent_name: str | None,
                            action: str, claims: dict, request: Request | None):
    """Build an audit callback for a source credential change."""
    return audit_credentials.credential_audit(
        action=action, provider=provider, tenant=tenant, agent_id=agent_id,
        agent_name=agent_name, claims=claims, secret=secret,
        decrypt_previous=lambda cfg: _plaintext_of_config(cfg, encrypted_key),
        request=request)


async def _connected_keys(agent, installation_store) -> set[str]:
    """Infer which sources have been configured for this worker."""
    import asyncio
    connected: set[str] = set()
    if agent is None:
        return connected
    cfg = agent.config or {}
    if cfg.get("github_credentials_added") and cfg.get("github_token_encrypted"):
        connected.add("github")
    if cfg.get("qiko_track_credentials_added") and cfg.get("qiko_track_token_encrypted"):
        connected.add("qiko_track")
    if cfg.get("slack_watched_channels"):
        try:
            inst = await asyncio.to_thread(installation_store.find_for_worker, agent.tenant, agent.id)
        except Exception:  # noqa: BLE001 - sync store may raise if the schema is not ready
            inst = None
        if inst is not None:
            connected.add("slack")
    return connected


@router.get("/agents/{agent_id}/sources")
async def list_sources(agent_id: str, request: Request,
                       tenant: str = Depends(authed_tenant),
                       agents: AgentService = Depends(get_agents),
                       catalog: SourceCatalog = Depends(get_source_catalog),
                       slack_oauth=Depends(get_slack_oauth)) -> list[dict]:
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    connected = await _connected_keys(agent, slack_oauth.store)
    await recheck()
    return catalog.items(connected=connected)


@router.get("/agents/{agent_id}/sources/{key}")
async def get_source(agent_id: str, key: str, request: Request,
                     tenant: str = Depends(authed_tenant),
                     agents: AgentService = Depends(get_agents),
                     catalog: SourceCatalog = Depends(get_source_catalog),
                     slack_oauth=Depends(get_slack_oauth)) -> dict:
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    connected = await _connected_keys(agent, slack_oauth.store)
    definition = catalog.definition(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="source not found")
    await recheck()
    return {
        "key": definition.key,
        "name": definition.name,
        "description": definition.description,
        "pollable": definition.pollable,
        "connected": key in connected,
    }


@router.post("/agents/{agent_id}/sources/{key}/verify")
async def verify_source(agent_id: str, key: str, body: VerifySourceBody, request: Request,
                        tenant: str = Depends(authed_tenant),
                        claims: dict = Depends(require_role(Role.editor)),
                        catalog: SourceCatalog = Depends(get_source_catalog)) -> dict:
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    try:
        connector = catalog.connector_for(key)
    except UnknownSource as e:
        raise HTTPException(status_code=404, detail="source not found") from e
    result = await connector.verify(config=body.config, credential=body.credential)
    await audit_credentials.record_credential_exercised(
        request.app.state.audit, provider=key, tenant=tenant, agent_id=agent_id,
        claims=claims, request=request)
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


@router.post("/agents/{agent_id}/sources/{key}")
async def connect_source(
    agent_id: str, key: str, request: Request,
    body: ConnectSourceBody = Body(default_factory=ConnectSourceBody),
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(current_claims),
    _role: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
    catalog: SourceCatalog = Depends(get_source_catalog),
    slack_oauth=Depends(get_slack_oauth),
) -> dict:
    """Store per-worker source credentials. Slack returns an OAuth install URL instead."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    definition = catalog.definition(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="source not found")

    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    if key == "slack":
        result = slack_oauth.create_install(tenant, agent_id, claims.get("sub"))
        await recheck()
        return result

    if key == "github":
        if not body.token:
            raise HTTPException(status_code=422, detail="GitHub token or installation id is required")
        meta = _SOURCE_CONFIG["github"]
        secret = body.token
        patch = {
            meta["added"]: True,
            meta["token"]: encrypt(secret),
            meta["allowlist"]: body.repo_allowlist,
            meta["watched_branches"]: body.watched_branches,
        }
    elif key == "qiko_track":
        if not body.token:
            raise HTTPException(status_code=422, detail="Qiko Track token is required")
        if not body.project_keys:
            raise HTTPException(status_code=422, detail="at least one project key is required")
        meta = _SOURCE_CONFIG["qiko_track"]
        secret = body.token
        patch = {
            meta["added"]: True,
            meta["token"]: encrypt(secret),
            meta["project_keys"]: body.project_keys,
            meta["base_url"]: body.base_url,
        }
    else:
        raise HTTPException(status_code=404, detail="source not found")

    await agents.update_config(
        tenant, agent_id, patch,
        audit=_build_credential_audit(
            provider=key, secret=secret, encrypted_key=meta["token"],
            tenant=tenant, agent_id=agent_id, agent_name=agent.name,
            action=audit_actions.CREDENTIAL_SET, claims=claims, request=request))
    await recheck()

    result: dict = {"connected": True}
    if key in ("qiko_track", "github"):
        try:
            if key == "qiko_track":
                ingest_config = {
                    "project_keys": body.project_keys,
                    "base_url": body.base_url,
                }
            else:
                ingest_config = {
                    "repo_allowlist": body.repo_allowlist,
                    "watched_branches": body.watched_branches,
                }
            result["ingested"] = await ingest_source(
                tenant, agent_id, key, ingest_config, secret,
                catalog=catalog,
                signal_store=request.app.state.intelligence_signal_store,
                knowledge=request.app.state.knowledge)
        except Exception as exc:  # noqa: BLE001 - a failed first ingest must not roll back the connection
            logger.warning("initial %s ingest failed for %s/%s: %s", key, tenant, agent_id, exc)
    return result


@router.get("/agents/{agent_id}/sources/github/install")
async def github_app_install(
    agent_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(current_claims),
    _role: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
) -> dict:
    """Return the GitHub App installation URL for this worker."""
    settings = get_settings()
    if not settings.github_app_slug:
        raise HTTPException(status_code=503, detail="GitHub App is not configured")
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        await recheck()
        raise HTTPException(status_code=404, detail="agent not found")
    state = jwt.encode(
        {"tenant": tenant, "agent_id": agent_id, "sub": claims.get("sub")},
        settings.session_secret,
        algorithm="HS256",
    )
    url = f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={state}"
    await recheck()
    return {"url": url}


@router.get("/sources/github/callback")
async def github_app_callback(
    request: Request,
    installation_id: str | None = None,
    setup_action: str = "",
    state: str = "",
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(current_claims),
    _role: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
) -> dict:
    """Store a GitHub App installation id after the user installs the app."""
    settings = get_settings()
    if not state:
        raise HTTPException(status_code=422, detail="missing state")
    try:
        payload = jwt.decode(state, settings.session_secret, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid state") from exc
    if payload.get("tenant") != tenant:
        raise HTTPException(status_code=403, detail="tenant mismatch")
    agent_id = payload.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=422, detail="missing agent id")
    if setup_action != "install" or not installation_id or not installation_id.isdigit():
        raise HTTPException(status_code=422, detail="missing installation id")
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    meta = _SOURCE_CONFIG["github"]
    secret = installation_id
    patch = {
        meta["added"]: True,
        meta["token"]: encrypt(secret),
        meta["allowlist"]: [],
        meta["watched_branches"]: [],
    }
    await agents.update_config(
        tenant, agent_id, patch,
        audit=_build_credential_audit(
            provider="github", secret=secret, encrypted_key=meta["token"],
            tenant=tenant, agent_id=agent_id, agent_name=agent.name,
            action=audit_actions.CREDENTIAL_SET, claims=claims, request=request))
    return {"connected": True}


@router.get("/agents/{agent_id}/sources/{key}/connection")
async def get_source_connection(
    agent_id: str, key: str, request: Request,
    tenant: str = Depends(authed_tenant),
    agents: AgentService = Depends(get_agents),
    catalog: SourceCatalog = Depends(get_source_catalog),
    slack_oauth=Depends(get_slack_oauth),
) -> dict:
    """Return the stored connection details for a source, without plaintext secrets."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    definition = catalog.definition(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="source not found")

    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    cfg = agent.config or {}
    await recheck()

    if key == "github":
        plaintext = _plaintext_of_config(cfg, _SOURCE_CONFIG["github"]["token"])
        return {
            "key": key,
            "connected": bool(cfg.get("github_credentials_added") and cfg.get("github_token_encrypted")),
            "token_masked": _mask(plaintext or ""),
            "repo_allowlist": cfg.get("github_repo_allowlist") or [],
            "watched_branches": cfg.get("github_watched_branches") or [],
        }
    if key == "qiko_track":
        plaintext = _plaintext_of_config(cfg, _SOURCE_CONFIG["qiko_track"]["token"])
        return {
            "key": key,
            "connected": bool(cfg.get("qiko_track_credentials_added") and cfg.get("qiko_track_token_encrypted")),
            "token_masked": _mask(plaintext or ""),
            "project_keys": cfg.get("qiko_track_project_keys") or [],
            "base_url": cfg.get("qiko_track_base_url") or "",
        }
    if key == "slack":
        inst = await _slack_installation_for_agent(slack_oauth.store, tenant, agent_id)
        return {
            "key": key,
            "connected": inst is not None and bool(cfg.get("slack_watched_channels")),
            "team_id": inst.team_id if inst else None,
            "watched_channels": cfg.get("slack_watched_channels") or [],
            "channels": [],
        }
    raise HTTPException(status_code=404, detail="source not found")


async def _slack_installation_for_agent(store, tenant: str, agent_id: str):
    import asyncio
    try:
        return await asyncio.to_thread(store.find_for_worker, tenant, agent_id)
    except Exception:  # noqa: BLE001
        return None


@router.delete("/agents/{agent_id}/sources/{key}")
async def disconnect_source(
    agent_id: str, key: str, request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(current_claims),
    _role: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
    catalog: SourceCatalog = Depends(get_source_catalog),
) -> dict:
    """Remove stored source credentials. Slack clears the watched channel list."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    definition = catalog.definition(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="source not found")

    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    if key == "github":
        meta = _SOURCE_CONFIG["github"]
        patch = {meta["added"]: False, meta["token"]: None, meta["allowlist"]: None, meta["watched_branches"]: None}
    elif key == "qiko_track":
        meta = _SOURCE_CONFIG["qiko_track"]
        patch = {
            meta["added"]: False, meta["token"]: None,
            meta["project_keys"]: None, meta["base_url"]: None,
        }
    elif key == "slack":
        meta = _SOURCE_CONFIG["slack"]
        patch = {meta["watched"]: None, meta["team_id"]: None}
    else:
        raise HTTPException(status_code=404, detail="source not found")

    audit_key = meta.get("token") or ""
    await agents.update_config(
        tenant, agent_id, patch,
        audit=_build_credential_audit(
            provider=key, secret=None, encrypted_key=audit_key,
            tenant=tenant, agent_id=agent_id, agent_name=agent.name,
            action=audit_actions.CREDENTIAL_REMOVED, claims=claims, request=request) if audit_key else None)
    await recheck()
    return {"disconnected": True}


@router.post("/agents/{agent_id}/sources/{key}/test")
async def test_source(
    agent_id: str, key: str, request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(current_claims),
    _role: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
    catalog: SourceCatalog = Depends(get_source_catalog),
    slack_oauth=Depends(get_slack_oauth),
) -> dict:
    """Test the stored source credential without mutating the third party."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    definition = catalog.definition(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="source not found")

    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    cfg = agent.config or {}

    if key in ("github", "qiko_track"):
        meta = _SOURCE_CONFIG[key]
        try:
            credential = stored_credential(
                cfg, flag=meta["added"], key=meta["token"], label=meta["label"])
        except HTTPException:
            await recheck()
            raise
        connector = catalog.connector_for(key)
        if key == "github":
            config = {
                "repo_allowlist": cfg.get(meta.get("allowlist", "")) or [],
                "watched_branches": cfg.get(meta.get("watched_branches", "")) or [],
            }
        else:
            config = {
                "project_keys": cfg.get(meta.get("project_keys", "")) or [],
                "base_url": cfg.get(meta.get("base_url", "")) or "",
            }
        result = await connector.verify(config=config, credential=credential)
        await audit_credentials.record_credential_exercised(
            request.app.state.audit, provider=key, tenant=tenant, agent_id=agent_id,
            claims=claims, request=request)
        await recheck()
        return result

    if key == "slack":
        inst = await _slack_installation_for_agent(slack_oauth.store, tenant, agent_id)
        if inst is None or not inst.bot_token:
            await recheck()
            raise HTTPException(status_code=422, detail="this worker has no Slack workspace installed")
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post("https://slack.com/api/auth.test", data={"token": inst.bot_token})
        body = r.json()
        await audit_credentials.record_credential_exercised(
            request.app.state.audit, provider="slack", tenant=tenant, agent_id=agent_id,
            claims=claims, request=request)
        await recheck()
        return {"ok": body.get("ok"), "team": body.get("team"), "error": body.get("error")}

    raise HTTPException(status_code=404, detail="source not found")


@router.post("/agents/{agent_id}/sources/slack/channels")
async def set_slack_watched_channels(
    agent_id: str, request: Request,
    body: SlackWatchChannelsBody,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(current_claims),
    _role: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
    slack_oauth=Depends(get_slack_oauth),
) -> dict:
    """Set the list of Slack channel IDs this worker should capture."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    inst = await _slack_installation_for_agent(slack_oauth.store, tenant, agent_id)
    if inst is None:
        raise HTTPException(status_code=422, detail="Slack workspace is not connected")

    def build_record(previous: dict) -> dict:
        return audit.build_row(audit.AuditEvent(
            action=audit_actions.WORKER_CONFIG_CHANGED, target_id=agent_id,
            target_label=agent.name, tenant_id=tenant,
            actor_type=audit.USER, actor_id=str(claims.get("sub") or ""),
            actor_label=str(claims.get("email") or claims.get("sub") or ""),
            changes={"slack_watched_channels": body.channel_ids},
            metadata={"previous": previous.get("slack_watched_channels")}))

    await agents.update_config(
        tenant, agent_id,
        {"slack_watched_channels": body.channel_ids, "slack_team_id": inst.team_id},
        audit=build_record)
    await recheck()
    return {"watched_channels": body.channel_ids}


@router.get("/agents/{agent_id}/sources/slack/channels")
async def list_slack_channels(
    agent_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    agents: AgentService = Depends(get_agents),
    slack_oauth=Depends(get_slack_oauth),
) -> dict:
    """Return watched channels. Full channel list is fetched from Slack in a later milestone."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    cfg = agent.config or {}
    await recheck()
    return {
        "watched_channels": cfg.get("slack_watched_channels") or [],
        "channels": [],
    }


@router.get("/agents/{agent_id}/discrepancies")
async def list_discrepancies(
    agent_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.admin)),
) -> list[dict]:
    """Surface claim-vs-evidence discrepancies for this worker. Owner/admin only."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    engine = DiscrepancyEngine(request.app.state.intelligence_signal_store)
    discrepancies = await engine.analyze(tenant, agent_id)
    await recheck()
    return [d.to_dict() for d in discrepancies]
