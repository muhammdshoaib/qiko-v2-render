"""Per-agent Intelligence Worker HTTP API -- tenant-scoped catalog, connection verification
and grounded chat over captured signals.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal

import jwt
from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.deps import (
    authed_tenant, current_claims, get_agents, get_chat, get_slack_oauth,
    require_role, resolve_tenant_worker, stored_credential,
)
from app.tasks.queue import EagerTaskQueue
from app.modules.audit import credentials as audit_credentials
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.agents.service import AgentService
from app.modules.identity.rbac import Role
from app.modules.intelligence.catalog import SourceCatalog, UnknownSource
from app.modules.intelligence.chat import IntelligenceChat
from app.modules.intelligence.discrepancies import DiscrepancyEngine
from app.modules.intelligence.documents import SUPPORTED_DOCUMENT_EXTENSIONS, UnsupportedDocumentError
from app.modules.intelligence.ingest import ingest_source
from app.modules.intelligence.orchestration import (
    Critic,
    Magistrate,
    Pipeline,
    PipelineConfig,
    Scout,
    Specialist,
    Synthesizer,
)
from app.modules.intelligence.backlog import BacklogCreateError, BacklogProposal, BacklogService, ProposedTicket
from app.modules.intelligence.qiko_track_client import QikoTrackClient, QikoTrackClientError
from app.modules.intelligence.qiko_track_metrics import MetricsService
from app.modules.sales_intelligence.ssrf import SsrfError
from app.modules.intelligence.research import Brief, ResearchService
from app.modules.knowledge.parsing import MAX_UPLOAD_BYTES
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
    project_name: str = Field(default="")
    project_kind: str = Field(default="")
    base_url: str = Field(default="")
    auto: bool = Field(default=False)

    @model_validator(mode="before")
    @classmethod
    def _normalize_project_keys(cls, values):
        if isinstance(values, dict) and values.get("project_key") and not values.get("project_keys"):
            values["project_keys"] = [values["project_key"]]
        return values


class SlackWatchChannelsBody(BaseModel):
    channel_ids: list[str] = Field(default_factory=list)


class PipelineRunCreate(BaseModel):
    subject: str = Field(min_length=1)
    facets: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _dedupe_and_cap_facets(self):
        seen: set[str] = set()
        unique: list[str] = []
        for facet in self.facets:
            if facet not in seen:
                seen.add(facet)
                unique.append(facet)
        self.facets = unique[:5]
        return self


class PipelineRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    tenant: str
    agent_id: str
    subject: str
    facets: list[str]
    status: dict
    verdict: str | None = None
    cost: dict | None = None


class FindingOut(BaseModel):
    text: str
    confidence: float | None = None
    evidence_refs: list[str] = []
    gaps: str = ""


class BriefOut(BaseModel):
    status: Literal["in_progress", "draft", "accepted"]
    summary: str
    findings: list[FindingOut]
    gaps: str
    citations: list[str]
    accepted_at: datetime | None = None


class ResearchRunOut(PipelineRunOut):
    brief: BriefOut | None = None


class ProposedTicketOut(BaseModel):
    title: str
    description_md: str
    type: Literal["FEATURE", "BUG", "CHORE", "SPIKE", "FINDING", "EPIC"]
    priority: Literal["URGENT", "HIGH", "MEDIUM", "LOW", "NONE"]
    estimate_points: int | None = None
    parent_index: int | None = None
    finding_index: int | None = None
    evidence_refs: list[str] = []


class ProposedTicketIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description_md: str = Field(default="", max_length=50_000)
    type: Literal["FEATURE", "BUG", "CHORE", "SPIKE", "FINDING", "EPIC"] = "FEATURE"
    priority: Literal["URGENT", "HIGH", "MEDIUM", "LOW", "NONE"] = "NONE"
    estimate_points: int | None = Field(default=None, ge=0, le=100)
    parent_index: int | None = None
    finding_index: int | None = None
    evidence_refs: list[str] = []


class BacklogProposalOut(BaseModel):
    project_key: str
    items: list[ProposedTicketOut]


class BacklogCreateBody(BaseModel):
    project_key: str | None = None
    items: list[ProposedTicketIn] = Field(min_length=1)


class DocumentOut(BaseModel):
    doc_id: str
    filename: str
    content_type: str
    size: int
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


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
        "service_token": "qiko_track_service_token",
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


def _qiko_track_credential(cfg: dict) -> str | None:
    """Resolve the effective Qiko Track token for this worker.

    Service-token mode reads from global settings at runtime so a rotation
    does not require reconnecting every worker. Manual mode decrypts the
    per-worker token stored by the user.
    """
    if cfg.get("qiko_track_service_token"):
        token = get_settings().qiko_track_service_token
        if token:
            return token
    try:
        return stored_credential(
            cfg, flag="qiko_track_credentials_added",
            key="qiko_track_token_encrypted", label="Qiko Track")
    except HTTPException:
        return None


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
    if cfg.get("qiko_track_credentials_added") and (cfg.get("qiko_track_token_encrypted") or cfg.get("qiko_track_service_token")):
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


@router.get("/agents/{agent_id}/sources/qiko_track/preview")
async def preview_qiko_track_source(
    agent_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
) -> dict:
    """Return whether auto-connect is available and a suggested project."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        await recheck()
        raise HTTPException(status_code=404, detail="agent not found")

    service_token = get_settings().qiko_track_service_token
    if not service_token:
        await recheck()
        return {"service_token_configured": False}

    base_url = get_settings().qiko_track_api_base
    client = QikoTrackClient(base_url, service_token)
    try:
        existing = await client.list_projects()
    except (QikoTrackClientError, SsrfError) as exc:
        await recheck()
        raise HTTPException(status_code=503, detail=f"could not reach Qiko Track: {exc}") from exc

    suggestion = _suggest_qiko_track_project(agent, existing)
    await recheck()
    return {
        "service_token_configured": True,
        "suggested": suggestion,
        "existing_projects": [{"key": p["key"], "name": p["name"], "kind": p.get("kind", "INTERNAL")} for p in existing],
    }


def _suggest_qiko_track_project(agent, existing_projects: list[dict]) -> dict:
    """Suggest a unique project key and name for this worker."""
    tenant = (getattr(agent, "tenant", "") or "").upper()
    name = (getattr(agent, "name", "") or "project").upper()
    prefix = "".join(ch for ch in (tenant + name) if ch.isalnum())[:6]
    if len(prefix) < 2:
        prefix = "QIW"
    existing_keys = {p["key"].upper() for p in existing_projects}
    counter = 1
    key = prefix
    while key in existing_keys and counter < 1000:
        suffix = str(counter)
        key = (prefix[:10 - len(suffix)] + suffix)[:10]
        counter += 1
    if key in existing_keys:
        key = prefix[:6] + "X"
    return {
        "key": key,
        "name": f"{agent.name} - Qiko Track",
        "kind": "INTERNAL",
    }


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


def _metrics_provider_for_agent(agent) -> Callable[[], Awaitable[dict[str, dict]]] | None:
    """Return a cached metrics loader for the agent's Qiko Track connection, or None."""
    if agent is None:
        return None
    cfg = agent.config or {}
    project_keys = cfg.get("qiko_track_project_keys") or []
    base_url = cfg.get("qiko_track_base_url") or ""
    if not project_keys or not base_url:
        return None
    token = _qiko_track_credential(cfg)
    if not token:
        return None
    service = MetricsService(base_url=base_url, token=token)
    return lambda: service.for_projects(project_keys)


@router.post("/agents/{agent_id}/chat/ask")
async def ask(
    agent_id: str, body: AskBody, request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
    chat: ChatService = Depends(get_chat),
    agents: AgentService = Depends(get_agents),
) -> dict:
    """Ask the intelligence worker a question grounded in its captured signals."""
    user_id = claims.get("sub", "public")
    worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    metrics_provider = _metrics_provider_for_agent(agent)
    intelligence = IntelligenceChat(worker)
    try:
        result = await intelligence.answer(
            body.question, conversation_id=body.conversation_id or None,
            chat=chat, user_id=user_id, metrics_provider=metrics_provider)
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
        s = get_settings()
        if not s.slack_client_id or not s.slack_client_secret or not s.slack_redirect_uri:
            raise HTTPException(status_code=503, detail="Slack integration is not configured")
        result = slack_oauth.create_install(tenant, agent_id, claims.get("sub"))
        await recheck()
        return result

    if key == "github":
        meta = _SOURCE_CONFIG["github"]
        if body.token:
            secret = body.token
        else:
            secret = stored_credential(
                agent.config or {}, flag=meta["added"], key=meta["token"], label=meta["label"])
        patch = {
            meta["added"]: True,
            meta["token"]: encrypt(secret),
            meta["allowlist"]: body.repo_allowlist,
            meta["watched_branches"]: body.watched_branches,
        }
    elif key == "qiko_track":
        meta = _SOURCE_CONFIG["qiko_track"]
        base_url = body.base_url or get_settings().qiko_track_api_base
        if body.auto:
            service_token = get_settings().qiko_track_service_token
            if not service_token:
                raise HTTPException(status_code=503, detail="Qiko Track auto-connect is not configured")
            secret = service_token
            client = QikoTrackClient(base_url, service_token)
            try:
                existing = await client.list_projects()
            except (QikoTrackClientError, SsrfError) as exc:
                raise HTTPException(status_code=503, detail=f"could not reach Qiko Track: {exc}") from exc

            project_key = (body.project_key or "").strip().upper()
            project_name = (body.project_name or "").strip()
            project_kind = (body.project_kind or "INTERNAL").upper()
            if project_kind not in ("PRODUCT", "CLIENT", "INTERNAL"):
                project_kind = "INTERNAL"

            if not project_key:
                suggestion = _suggest_qiko_track_project(agent, existing)
                project_key = suggestion["key"]
                project_name = project_name or suggestion["name"]

            existing_keys = {p["key"].upper() for p in existing}
            if project_key not in existing_keys:
                if not project_name:
                    project_name = f"{agent.name} - Qiko Track"
                idempotency_key = f"qiko-v2:{tenant}:{agent_id}:{project_key}"
                try:
                    await client.create_project(
                        {"key": project_key, "name": project_name, "kind": project_kind},
                        idempotency_key=idempotency_key,
                    )
                except (QikoTrackClientError, SsrfError) as exc:
                    raise HTTPException(status_code=502, detail=f"Qiko Track project creation failed: {exc}") from exc

            seen = {project_key}
            project_keys = [project_key]
            for p in existing:
                key = (p.get("key") or "").upper()
                if key and key not in seen:
                    seen.add(key)
                    project_keys.append(key)
            patch = {
                meta["added"]: True,
                meta["service_token"]: True,
                meta["token"]: "",
                meta["project_keys"]: project_keys,
                meta["base_url"]: base_url,
            }
        else:
            if body.token:
                secret = body.token
            else:
                secret = stored_credential(
                    agent.config or {}, flag=meta["added"], key=meta["token"], label=meta["label"])
            project_keys = body.project_keys
            if not project_keys:
                project_keys = agent.config.get(meta["project_keys"]) or [] if agent.config else []
            if not project_keys:
                raise HTTPException(status_code=422, detail="at least one project key is required")
            patch = {
                meta["added"]: True,
                meta["service_token"]: False,
                meta["token"]: encrypt(secret),
                meta["project_keys"]: project_keys,
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
                    "project_keys": project_keys,
                    "base_url": base_url,
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
) -> HTMLResponse:
    """Store a GitHub App installation id after the user installs the app.

    Returns a small HTML page that closes the popup (so the parent window can
    refresh the connection state) or redirects if the page was opened directly.
    """
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
    redirect_url = f"{settings.frontend_url.rstrip('/')}/workers/{agent_id}?tab=Sources"
    html = (
        "<html><head><title>GitHub connected</title></head><body>"
        "<p>GitHub connected. You can close this window.</p>"
        "<script>"
        "if (window.opener) { window.opener.postMessage({ type: 'github-connected' }, '*'); window.close(); }"
        f"else {{ window.location.href = '{redirect_url}'; }}"
        "</script>"
        "</body></html>"
    )
    return HTMLResponse(content=html)


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
        service_token_used = bool(cfg.get("qiko_track_service_token"))
        token_available = cfg.get("qiko_track_token_encrypted") or service_token_used
        return {
            "key": key,
            "connected": bool(cfg.get("qiko_track_credentials_added") and token_available),
            "service_token_used": service_token_used,
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


@router.get("/agents/{agent_id}/metrics")
async def get_agent_metrics(
    agent_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.viewer)),
    agents: AgentService = Depends(get_agents),
) -> dict[str, dict]:
    """Read Qiko Track delivery metrics for the projects connected to this worker."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        await recheck()
        raise HTTPException(status_code=404, detail="agent not found")

    cfg = agent.config or {}
    project_keys = cfg.get("qiko_track_project_keys") or []
    base_url = cfg.get("qiko_track_base_url") or ""
    if not project_keys or not base_url:
        await recheck()
        return {"projects": {}}

    token = _qiko_track_credential(cfg)
    if not token:
        await recheck()
        return {"projects": {}}
    service = MetricsService(base_url=base_url, token=token)
    try:
        metrics = await service.for_projects(project_keys)
    finally:
        await recheck()
    return {"projects": metrics}


@router.post("/agents/{agent_id}/documents")
async def upload_document(
    agent_id: str, request: Request,
    file: UploadFile = File(...),
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
) -> DocumentOut:
    """Upload a document to a worker. Parsing and ingestion run off the request path."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    if file.filename is None or not any(file.filename.lower().endswith(f".{ext}")
                                        for ext in SUPPORTED_DOCUMENT_EXTENSIONS):
        raise HTTPException(status_code=422, detail="unsupported or missing file extension")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"file exceeds {MAX_UPLOAD_BYTES} bytes")
    actor = str(claims.get("email") or claims.get("sub") or "unknown")
    try:
        doc = await request.app.state.document_service.upload(
            tenant=tenant, agent_id=agent_id, filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            data=data, actor=actor)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    await audit.record(
        request.app.state.audit,
        audit.AuditEvent(
            action=audit_actions.DOCUMENT_INGESTED,
            target_id=doc.doc_id,
            target_label=doc.filename,
            tenant_id=tenant,
            actor_type=audit.USER,
            actor_id=str(claims.get("sub") or ""),
            actor_label=str(claims.get("email") or claims.get("sub") or ""),
            changes={"doc_id": doc.doc_id, "chunks": 0},
            metadata={"agent_id": agent_id, "size": doc.size},
        ),
        request=request,
    )
    await recheck()
    return DocumentOut.model_validate(doc, from_attributes=True)


@router.get("/agents/{agent_id}/documents")
async def list_documents(
    agent_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.viewer)),
) -> list[DocumentOut]:
    """List documents uploaded to this worker."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    docs = await request.app.state.document_service.list(tenant, agent_id)
    await recheck()
    return [DocumentOut.model_validate(d, from_attributes=True) for d in docs]


@router.delete("/agents/{agent_id}/documents/{doc_id}")
async def delete_document(
    agent_id: str, doc_id: str, request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
) -> dict:
    """Delete an uploaded document and all derived passages and signals."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    doc = await request.app.state.document_service.document_store.get(tenant, agent_id, doc_id)
    if doc is None:
        await recheck()
        raise HTTPException(status_code=404, detail="document not found")
    await request.app.state.document_service.delete(tenant, agent_id, doc_id)
    await audit.record(
        request.app.state.audit,
        audit.AuditEvent(
            action=audit_actions.DOCUMENT_DELETED,
            target_id=doc_id,
            target_label=doc.filename,
            tenant_id=tenant,
            actor_type=audit.USER,
            actor_id=str(claims.get("sub") or ""),
            actor_label=str(claims.get("email") or claims.get("sub") or ""),
            changes={"doc_id": doc_id, "passages_removed": 0},
            metadata={"agent_id": agent_id},
        ),
        request=request,
    )
    await recheck()
    return {"deleted": True}


def _build_pipeline_for_request(request: Request, worker: object) -> Pipeline:
    """Assemble a Pipeline from request-scoped services and a resolved worker."""
    return Pipeline(
        scout=Scout(
            request.app.state.knowledge,
            signal_store=request.app.state.intelligence_signal_store,
            document_store=request.app.state.intelligence_document_store,
        ),
        specialist=Specialist(worker),
        synthesizer=Synthesizer(worker.agent.generator),
        critic=Critic(),
        magistrate=Magistrate(threshold=worker.agent.threshold),
        store=request.app.state.pipeline_run_store,
    )


@router.post("/agents/{agent_id}/pipeline/runs")
async def create_pipeline_run(
    agent_id: str,
    body: PipelineRunCreate,
    request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
) -> PipelineRunOut:
    """Start a new intelligence pipeline run. The run is persisted immediately and the heavy
    work is executed by the task queue so the API returns without blocking."""
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    config = PipelineConfig(
        tenant=tenant, agent_id=agent_id, subject=body.subject, facets=body.facets)
    run = Pipeline.new_run(config)
    await request.app.state.pipeline_run_store.add(run)

    await audit.record(
        request.app.state.audit,
        audit.AuditEvent(
            action=audit_actions.PIPELINE_RUN_STARTED,
            target_id=run.run_id,
            target_label=run.subject,
            tenant_id=tenant,
            actor_type=audit.USER,
            actor_id=str(claims.get("sub") or ""),
            actor_label=str(claims.get("email") or claims.get("sub") or ""),
            changes=audit.diff(
                audit_actions.PIPELINE_RUN_STARTED, {},
                {"subject": run.subject, "facets": run.facets}),
            metadata={"agent_id": agent_id},
        ),
        request=request,
    )

    task_queue = request.app.state.task_queue
    if isinstance(task_queue, EagerTaskQueue):
        worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
        try:
            pipeline = _build_pipeline_for_request(request, worker)
            await task_queue.enqueue(
                "run_intelligence_pipeline",
                tenant=tenant, agent_id=agent_id, run_id=run.run_id, pipeline=pipeline)
        finally:
            await recheck()
    else:  # pragma: no cover - arq prod path (Redis carries only the serialisable ids)
        await task_queue.enqueue(
            "run_intelligence_pipeline", tenant=tenant, agent_id=agent_id, run_id=run.run_id)

    return PipelineRunOut.model_validate(run)


@router.get("/agents/{agent_id}/pipeline/runs/{run_id}")
async def get_pipeline_run(
    agent_id: str,
    run_id: str,
    request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.viewer)),
) -> PipelineRunOut:
    """Read the current status of a pipeline run."""
    run = await request.app.state.pipeline_run_store.get(tenant, agent_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return PipelineRunOut.model_validate(run)


@router.post("/agents/{agent_id}/pipeline/runs/{run_id}/resume")
async def resume_pipeline_run(
    agent_id: str,
    run_id: str,
    request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
) -> PipelineRunOut:
    """Resume an existing pipeline run (e.g. after a retry or an explicit re-run request)."""
    run = await request.app.state.pipeline_run_store.get(tenant, agent_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")

    await audit.record(
        request.app.state.audit,
        audit.AuditEvent(
            action=audit_actions.PIPELINE_RUN_RESUMED,
            target_id=run.run_id,
            target_label=run.subject,
            tenant_id=tenant,
            actor_type=audit.USER,
            actor_id=str(claims.get("sub") or ""),
            actor_label=str(claims.get("email") or claims.get("sub") or ""),
            changes=audit.diff(audit_actions.PIPELINE_RUN_RESUMED, {}, {"resumed": True}),
            metadata={"agent_id": agent_id},
        ),
        request=request,
    )

    task_queue = request.app.state.task_queue
    if isinstance(task_queue, EagerTaskQueue):
        worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
        try:
            pipeline = _build_pipeline_for_request(request, worker)
            await task_queue.enqueue(
                "run_intelligence_pipeline",
                tenant=tenant, agent_id=agent_id, run_id=run_id, pipeline=pipeline)
        finally:
            await recheck()
    else:  # pragma: no cover - arq prod path
        await task_queue.enqueue(
            "run_intelligence_pipeline", tenant=tenant, agent_id=agent_id, run_id=run_id)

    return PipelineRunOut.model_validate(run)


def _brief_out(brief: Brief | None) -> BriefOut | None:
    if brief is None:
        return None
    return BriefOut(
        status=brief.status,
        summary=brief.summary,
        findings=[
            FindingOut(
                text=f.text,
                confidence=f.confidence,
                evidence_refs=list(f.evidence_refs),
                gaps=f.gaps,
            )
            for f in brief.findings
        ],
        gaps=brief.gaps,
        citations=list(brief.citations),
        accepted_at=brief.accepted_at,
    )


def _research_service_for_request(
    request: Request, *, worker: object | None = None,
) -> ResearchService:
    return ResearchService(
        store=request.app.state.pipeline_run_store,
        knowledge=request.app.state.knowledge,
        signal_store=request.app.state.intelligence_signal_store,
        worker=worker,
    )


def _backlog_service_for_agent(agent) -> BacklogService | None:
    """Return a BacklogService for the agent's Qiko Track connection, or None."""
    if agent is None:
        return None
    cfg = agent.config or {}
    project_keys = cfg.get("qiko_track_project_keys") or []
    base_url = cfg.get("qiko_track_base_url") or ""
    if not project_keys or not base_url:
        return None
    token = _qiko_track_credential(cfg)
    if not token:
        return None
    return BacklogService(base_url=base_url, token=token)


def _is_research_run(run) -> bool:
    return (run.status or {}).get("config", {}).get("kind") == "research"


@router.post("/agents/{agent_id}/research/runs")
async def create_research_run(
    agent_id: str,
    body: PipelineRunCreate,
    request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
) -> ResearchRunOut:
    """Start a research run for a subject. The run is persisted and executed by the task queue."""
    agent = await agents.get(tenant, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    svc = _research_service_for_request(request)
    run = await svc.start(tenant, agent_id, body.subject, body.facets)

    await audit.record(
        request.app.state.audit,
        audit.AuditEvent(
            action=audit_actions.PIPELINE_RUN_STARTED,
            target_id=run.run_id,
            target_label=run.subject,
            tenant_id=tenant,
            actor_type=audit.USER,
            actor_id=str(claims.get("sub") or ""),
            actor_label=str(claims.get("email") or claims.get("sub") or ""),
            changes=audit.diff(
                audit_actions.PIPELINE_RUN_STARTED, {},
                {"subject": run.subject, "facets": run.facets, "kind": "research"}),
            metadata={"agent_id": agent_id, "kind": "research"},
        ),
        request=request,
    )

    task_queue = request.app.state.task_queue
    if isinstance(task_queue, EagerTaskQueue):
        worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
        try:
            pipeline = _build_pipeline_for_request(request, worker)
            await task_queue.enqueue(
                "run_intelligence_pipeline",
                tenant=tenant, agent_id=agent_id, run_id=run.run_id, pipeline=pipeline)
        finally:
            await recheck()
    else:  # pragma: no cover - arq prod path
        await task_queue.enqueue(
            "run_intelligence_pipeline", tenant=tenant, agent_id=agent_id, run_id=run.run_id)

    out = ResearchRunOut.model_validate(run)
    out.brief = _brief_out(await svc.get_brief(tenant, agent_id, run.run_id))
    return out


@router.get("/agents/{agent_id}/research/runs/{run_id}")
async def get_research_run(
    agent_id: str,
    run_id: str,
    request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.viewer)),
) -> ResearchRunOut:
    """Read a research run and its current brief."""
    run = await request.app.state.pipeline_run_store.get(tenant, agent_id, run_id)
    if run is None or not _is_research_run(run):
        raise HTTPException(status_code=404, detail="research run not found")

    svc = _research_service_for_request(request)
    brief = await svc.get_brief(tenant, agent_id, run_id)
    out = ResearchRunOut.model_validate(run)
    out.brief = _brief_out(brief)
    return out


@router.post("/agents/{agent_id}/research/runs/{run_id}/accept")
async def accept_research_run(
    agent_id: str,
    run_id: str,
    request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
) -> ResearchRunOut:
    """Accept the brief from a completed research run and make it ground truth."""
    run = await request.app.state.pipeline_run_store.get(tenant, agent_id, run_id)
    if run is None or not _is_research_run(run):
        raise HTTPException(status_code=404, detail="research run not found")

    worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    try:
        svc = _research_service_for_request(request, worker=worker)
        brief = await svc.accept_brief(
            tenant, agent_id, run_id, actor=str(claims.get("sub") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        await recheck()

    if brief is None:
        raise HTTPException(status_code=404, detail="research run not found")

    await audit.record(
        request.app.state.audit,
        audit.AuditEvent(
            action=audit_actions.RESEARCH_BRIEF_ACCEPTED,
            target_id=run_id,
            target_label=run.subject,
            tenant_id=tenant,
            actor_type=audit.USER,
            actor_id=str(claims.get("sub") or ""),
            actor_label=str(claims.get("email") or claims.get("sub") or ""),
            changes=audit.diff(audit_actions.RESEARCH_BRIEF_ACCEPTED, {}, {"accepted": True}),
            metadata={"agent_id": agent_id, "run_id": run_id},
        ),
        request=request,
    )

    out = ResearchRunOut.model_validate(run)
    out.brief = _brief_out(brief)
    return out


@router.get("/agents/{agent_id}/research/runs/{run_id}/backlog")
async def get_backlog_proposal(
    agent_id: str,
    run_id: str,
    request: Request,
    tenant: str = Depends(authed_tenant),
    _claims: dict = Depends(require_role(Role.viewer)),
    agents: AgentService = Depends(get_agents),
) -> BacklogProposalOut:
    """Generate a reviewable Qiko Track backlog draft from an accepted research brief."""
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    try:
        run = await request.app.state.pipeline_run_store.get(tenant, agent_id, run_id)
        if run is None or not _is_research_run(run):
            raise HTTPException(status_code=404, detail="research run not found")

        agent = await agents.get(tenant, agent_id)
        service = _backlog_service_for_agent(agent)
        if service is None:
            raise HTTPException(status_code=422, detail="this worker has no Qiko Track connection")

        project_keys = (agent.config or {}).get("qiko_track_project_keys") or []
        project_key = project_keys[0]

        svc = _research_service_for_request(request)
        brief = await svc.get_brief(tenant, agent_id, run_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="research run not found")

        proposal = service.propose(brief, project_key)
    finally:
        await recheck()
    return BacklogProposalOut(project_key=proposal.project_key, items=[
        ProposedTicketOut(**item.to_dict()) for item in proposal.items
    ])


@router.post("/agents/{agent_id}/research/runs/{run_id}/backlog")
async def create_backlog_tickets(
    agent_id: str,
    run_id: str,
    body: BacklogCreateBody,
    request: Request,
    tenant: str = Depends(authed_tenant),
    claims: dict = Depends(require_role(Role.editor)),
    agents: AgentService = Depends(get_agents),
) -> dict:
    """Create the approved subset of proposed tickets in Qiko Track.

    Each creation is idempotent; resubmitting the same approval cannot duplicate tickets.
    """
    _worker, recheck = await _resolve_worker(request, tenant, agent_id)
    try:
        run = await request.app.state.pipeline_run_store.get(tenant, agent_id, run_id)
        if run is None or not _is_research_run(run):
            raise HTTPException(status_code=404, detail="research run not found")

        agent = await agents.get(tenant, agent_id)
        service = _backlog_service_for_agent(agent)
        if service is None:
            raise HTTPException(status_code=422, detail="this worker has no Qiko Track connection")

        cfg = agent.config or {}
        project_keys = cfg.get("qiko_track_project_keys") or []
        project_key = body.project_key or (project_keys[0] if project_keys else "")
        if not project_key:
            raise HTTPException(status_code=422, detail="no project key available")

        proposal = BacklogProposal(
            project_key=project_key,
            items=[
                ProposedTicket(
                    title=item.title,
                    description_md=item.description_md,
                    type=item.type,
                    priority=item.priority,
                    estimate_points=item.estimate_points,
                    parent_index=item.parent_index,
                    finding_index=item.finding_index,
                    evidence_refs=list(item.evidence_refs),
                )
                for item in body.items
            ],
        )
        try:
            created = await service.create_approved(proposal, set(range(len(proposal.items))))
        except BacklogCreateError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        await audit.record(
            request.app.state.audit,
            audit.AuditEvent(
                action=audit_actions.BACKLOG_CREATED,
                target_id=run_id,
                target_label=run.subject,
                tenant_id=tenant,
                actor_type=audit.USER,
                actor_id=str(claims.get("sub") or ""),
                actor_label=str(claims.get("email") or claims.get("sub") or ""),
                changes=audit.diff(
                    audit_actions.BACKLOG_CREATED, {},
                    {"created": len(created), "project_key": project_key}),
                metadata={"agent_id": agent_id, "run_id": run_id, "created_keys": [c["key"] for c in created]},
            ),
            request=request,
        )
    finally:
        await recheck()
    return {"created": created}
