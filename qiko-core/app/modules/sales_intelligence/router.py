"""IDG Sales Intelligence HTTP API -- tenant-scoped equivalent of
app/Http/Controllers/Api/IdgSales/IdgSalesController.php.

Route shape follows qiko-core's existing per-agent module convention (see app.modules.crm.router):
`/sales-intelligence/{agent_id}/...` under the `/api/v1` prefix, instead of the Laravel branch's
`/api/avatar/idg-sales/{agentId}/...`. All endpoints are tenant-scoped via `authed_tenant`
(BOLA-safe -- tenant comes from the verified access-token claims, never a client-supplied header).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.core.deps import (
    WorkerUnavailable,
    authed_tenant,
    require_available_worker,
    require_role,
    resolve_tenant_worker,
)
from app.modules.identity.rbac import Role
from app.modules.sales_intelligence.models import (
    ACTIVITY_TYPES,
    MANUAL_TRANSITION_STAGES,
    RECOMMENDATIONS,
    REVIEW_DECISIONS,
    SCAN_CADENCES,
    SOURCE_STATUSES,
    STAGES,
    merge_ingest_filter,
)
from app.modules.sales_intelligence import source_catalog
from app.modules.sales_intelligence.salesforce import SalesforceError, SalesforceNotConfiguredError
from app.modules.sales_intelligence.service import (
    InvalidStageTransitionError,
    OpportunityNotFoundError,
    SalesIntelligenceError,
    SourceInactiveError,
)

# Upper bound on an opportunities-list page. `limit=all` (or any oversized value) is clamped to
# this so the "show all" views work without an unbounded query that could be abused.
MAX_OPPORTUNITY_LIMIT = 1000

router = APIRouter(prefix="/sales-intelligence", tags=["sales-intelligence"])


def get_sales_intel(request: Request):
    return request.app.state.sales_intel


def get_sales_intel_mutation(request: Request):
    return request.app.state.sales_intel_mutation


def get_salesforce_auth(request: Request):
    return request.app.state.salesforce_auth


def get_ingest_filters(request: Request):
    return request.app.state.sales_intel_ingest_filters


def get_salesforce_push(request: Request):
    return request.app.state.salesforce_push


def _actor_user_id(claims: dict) -> str | None:
    return claims.get("sub") or claims.get("user_id")


async def _resolve_worker(request: Request, tenant: str, agent_id: str):
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    return recheck


async def _agent_config(request: Request, tenant: str, agent_id: str) -> dict | None:
    """Resolve the per-agent free-form config so qualification can read its si_* keys
    (si_service_keywords / si_target_countries / si_technology_keywords). Returns None when the
    agent is unknown, so the scorer falls back to the IDG defaults."""
    agents = getattr(request.app.state, "agents", None)
    if agents is None:
        return None
    agent = await agents.get(tenant, agent_id)
    return getattr(agent, "config", None) if agent is not None else None


def _source_out(s, *, scan_interval_minutes: int = 1) -> dict:
    return {
        "id": s.id, "agentId": s.agent_id, "sourceKey": s.source_key, "name": s.name, "type": s.type,
        "status": s.status, "authStatus": s.auth_status, "scanCadence": s.scan_cadence,
        "lastScanStatus": s.last_scan_status, "lastScanAt": s.last_scan_at,
        "nextScanAt": s.next_scan_at(scan_interval_minutes=scan_interval_minutes),
        "opportunitiesFound": s.opportunities_found,
        "lastError": s.last_error, "config": s.config, "createdAt": s.created_at, "updatedAt": s.updated_at,
    }


def _opportunity_out(o, *, detail_service=None) -> dict:
    out = {
        "id": o.id, "agentId": o.agent_id, "externalId": o.external_id, "sourceKey": o.source_key,
        "source": o.source_name, "sourceUrl": o.source_url,
        "isManual": (o.raw_payload or {}).get("origin") == "manual" or str(o.external_id).startswith("manual-"),
        "title": o.title, "buyer": o.buyer, "country": o.country, "region": o.region, "category": o.category,
        "estimatedValue": o.estimated_value, "currency": o.currency, "publishedAt": o.published_at,
        "deadlineAt": o.deadline_at, "stage": o.stage, "recommendation": o.recommendation,
        "qualificationScore": o.qualification_score, "confidence": o.confidence,
        "competitorReadiness": o.competitor_readiness, "qualificationSummary": o.qualification_summary,
        "qualificationReasons": o.qualification_reasons, "qualificationDimensions": o.qualification_dimensions,
        "qualificationRecommendations": o.qualification_recommendations, "rejectionReasons": o.rejection_reasons,
        "risks": o.risks, "missingFields": o.missing_fields, "humanReviewStatus": o.human_review_status,
        "humanReviewNotes": o.human_review_notes, "reviewedAt": o.reviewed_at,
        "assignedReviewerUserId": o.assigned_reviewer_user_id, "assignedReviewerName": o.assigned_reviewer_name,
        "assignedByUserId": o.assigned_by_user_id, "assignedAt": o.assigned_at, "archivedAt": o.archived_at,
        "isArchived": o.is_archived(), "deletedAt": o.deleted_at,
        "salesforcePushStatus": o.salesforce_push_status, "salesforceOpportunityId": o.salesforce_opportunity_id,
        "salesforcePushedAt": o.salesforce_pushed_at, "salesforcePushError": o.salesforce_push_error,
        "createdAt": o.created_at, "updatedAt": o.updated_at,
    }
    if detail_service is not None:
        out["detail"] = detail_service.build(o)
    return out


def _log_out(log) -> dict:
    return {
        "id": log.id, "agentId": log.agent_id, "opportunityId": log.opportunity_id, "actorUserId": log.actor_user_id,
        "activityType": log.activity_type, "action": log.action, "detail": log.detail, "tone": log.tone,
        "changes": (log.metadata or {}).get("changes"), "metadata": log.metadata, "createdAt": log.created_at,
    }


_DECISION_LABELS = {"approved": "Approved", "rejected": "Rejected", "needs_review": "Override"}


def _decision_out(log) -> dict:
    """Shape one human-review activity-log entry as a decision-history record -- port of
    IdgSalesDecisionHistoryResource (decision + label + reviewer + timestamp)."""
    metadata = log.metadata or {}
    decision = metadata.get("decision") if isinstance(metadata.get("decision"), str) else None
    return {
        "id": log.id, "agentId": log.agent_id, "opportunityId": log.opportunity_id,
        "action": log.action, "decision": decision,
        "decisionLabel": _DECISION_LABELS.get(decision, decision.replace("_", " ").title() if decision else "Decision"),
        "detail": log.detail, "tone": log.tone, "reviewerUserId": log.actor_user_id,
        "metadata": metadata, "createdAt": log.created_at,
    }


def _salesforce_out(c, auth) -> dict:
    from app.core.config import get_settings

    s = get_settings()
    return {
        "connected": c.is_connected(), "status": c.status, "instanceUrl": c.instance_url,
        "salesforceUserId": c.salesforce_user_id, "salesforceOrgId": c.salesforce_org_id,
        "connectedAt": c.connected_at, "tokenExpiresAt": c.token_expires_at, "lastError": c.last_error,
        "configured": bool(s.salesforce_client_id and s.salesforce_client_secret),
        "oauthCallbackUrl": auth.redirect_uri(),
    }


@router.get("/{agent_id}/sources")
async def sources(agent_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    await svc.ensure_sources(tenant, agent_id)
    items = await svc.sources.list_for_agent(tenant, agent_id)
    return {"sources": [_source_out(s, scan_interval_minutes=svc.scan_interval_minutes) for s in items]}


def _ingest_filter_out(setting) -> dict:
    return {
        "agentId": setting.agent_id,
        "queryEnabled": setting.query_enabled,
        "queryKeyword": setting.query_keyword,
        "allCountries": setting.all_countries,
        "allCategories": setting.all_categories,
        "updatedAt": setting.updated_at.isoformat() if setting.updated_at else None,
    }


class IngestFilterBody(BaseModel):
    # All optional so the FE can patch any subset. Mirrors Staging config.ingest_filters.
    query_enabled: bool | None = None
    query_keyword: str | None = Field(default=None, max_length=255)
    all_countries: bool | None = None
    all_categories: bool | None = None


@router.get("/{agent_id}/ingest-filters")
async def ingest_filters(agent_id: str, tenant: str = Depends(authed_tenant),
                         store=Depends(get_ingest_filters)) -> dict:
    return _ingest_filter_out(await store.get_or_create(tenant, agent_id))


@router.patch("/{agent_id}/ingest-filters")
async def update_ingest_filters(agent_id: str, body: IngestFilterBody, tenant: str = Depends(authed_tenant),
                                claims: dict = Depends(require_role(Role.editor)),
                                store=Depends(get_ingest_filters)) -> dict:
    setting = await store.get_or_create(tenant, agent_id)
    data = body.model_dump(exclude_none=True)
    if "query_enabled" in data:
        setting.query_enabled = data["query_enabled"]
    if "query_keyword" in data:
        setting.query_keyword = data["query_keyword"]
    if "all_countries" in data:
        setting.all_countries = data["all_countries"]
    if "all_categories" in data:
        setting.all_categories = data["all_categories"]
    return _ingest_filter_out(await store.update(setting))


@router.get("/{agent_id}/sources/catalog")
async def sources_catalog(agent_id: str, tenant: str = Depends(authed_tenant),
                          svc=Depends(get_sales_intel)) -> dict:
    """First-party portal catalog (TED/UNGM) annotated with whether the agent already has each
    source attached. Custom sources are not part of the catalog; they appear in GET /sources."""
    attached = {s.source_key for s in await svc.sources.list_for_agent(tenant, agent_id)}
    return {"catalog": [source_catalog.catalog_item_out(d, already_added=d["key"] in attached)
                        for d in source_catalog.DEFINITIONS]}


# Source key format (mirrors Staging storeSource): a letter then letters/digits/_/-, 2-64 chars.
# Normalised to lowercase. Custom keys are allowed as long as the format is valid and (for PATCH/
# DELETE) the source is actually attached; the service rejects unknown/unattached keys.
_SOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def _norm_source_key(source_key: str) -> str:
    key = (source_key or "").strip().lower()
    if not _SOURCE_KEY_RE.match(key):
        raise HTTPException(status_code=422, detail="invalid source_key")
    return key


class StoreSourceBody(BaseModel):
    # Attach a catalog portal (ted/ungm) or a custom source. `name` is required for custom sources;
    # `config.url` is required for custom sources (the portal/search URL to scan).
    source_key: str = Field(min_length=2, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    config: dict | None = None


class UpdateSourceBody(BaseModel):
    # Both optional so the FE can patch either the on/off status or the scheduled scan cadence
    # independently (mirrors Ali's UpdateIdgSalesSourcePayload). At least one must be supplied.
    status: str | None = None
    scan_cadence: str | None = None


@router.post("/{agent_id}/sources")
async def store_source(agent_id: str, body: StoreSourceBody, tenant: str = Depends(authed_tenant),
                       claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel)) -> dict:
    source_key = _norm_source_key(body.source_key)
    try:
        source = await svc.attach_source(tenant, agent_id, source_key, name=body.name,
                                         config_input=body.config, actor_user_id=_actor_user_id(claims))
    except SalesIntelligenceError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"source": _source_out(source, scan_interval_minutes=svc.scan_interval_minutes)}


@router.delete("/{agent_id}/sources/{source_key}")
async def delete_source(agent_id: str, source_key: str, tenant: str = Depends(authed_tenant),
                        claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel)) -> dict:
    key = _norm_source_key(source_key)
    try:
        await svc.detach_source(tenant, agent_id, key, actor_user_id=_actor_user_id(claims))
    except OpportunityNotFoundError as e:
        raise HTTPException(status_code=404, detail="source not attached") from e
    except SalesIntelligenceError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"ok": True, "sourceKey": key}


@router.patch("/{agent_id}/sources/{source_key}")
async def update_source(agent_id: str, source_key: str, body: UpdateSourceBody,
                        tenant: str = Depends(authed_tenant), claims: dict = Depends(require_role(Role.editor)),
                        svc=Depends(get_sales_intel)) -> dict:
    key = _norm_source_key(source_key)
    if body.status is None and body.scan_cadence is None:
        raise HTTPException(status_code=422, detail="status or scan_cadence is required")
    if body.status is not None and body.status not in SOURCE_STATUSES:
        raise HTTPException(status_code=422, detail="invalid status")
    if body.scan_cadence is not None and body.scan_cadence not in SCAN_CADENCES:
        raise HTTPException(status_code=422, detail="invalid scan_cadence")
    actor = _actor_user_id(claims)
    source = None
    try:
        if body.status is not None:
            source = await svc.update_source_status(tenant, agent_id, key, body.status, actor)
        if body.scan_cadence is not None:
            source = await svc.update_source_cadence(tenant, agent_id, key, body.scan_cadence, actor)
    except OpportunityNotFoundError as e:
        raise HTTPException(status_code=404, detail="source not attached") from e
    except SalesIntelligenceError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"source": _source_out(source, scan_interval_minutes=svc.scan_interval_minutes)}


class ScanBody(BaseModel):
    query: str | None = None
    title: str | None = None
    page_size: int | None = None
    page_index: int | None = None
    limit: int | None = None
    active_only: bool | None = None
    country_allowlist: str | None = None
    category_allowlist: str | None = None


@router.post("/{agent_id}/scan/ungm")
async def scan_ungm(agent_id: str, body: ScanBody, request: Request, tenant: str = Depends(authed_tenant),
                    claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel),
                    filters_store=Depends(get_ingest_filters)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    setting = await filters_store.get_or_create(tenant, agent_id)
    try:
        result = await svc.scan_ungm(
            tenant, agent_id, merge_ingest_filter(body.model_dump(exclude_none=True), setting), _actor_user_id(claims),
            agent_config=await _agent_config(request, tenant, agent_id),
            recheck_worker=recheck)
    except SourceInactiveError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except WorkerUnavailable:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    await recheck()
    return {
        "source": _source_out(result["source"], scan_interval_minutes=svc.scan_interval_minutes),
        "opportunities": [_opportunity_out(o) for o in result["opportunities"]],
        "summary": {"created": result["created"], "updated": result["updated"],
                    "totalReturned": len(result["opportunities"])},
    }


@router.post("/{agent_id}/scan/ted")
async def scan_ted(agent_id: str, body: ScanBody, request: Request, tenant: str = Depends(authed_tenant),
                   claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel),
                   filters_store=Depends(get_ingest_filters)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    setting = await filters_store.get_or_create(tenant, agent_id)
    try:
        result = await svc.scan_ted(
            tenant, agent_id, merge_ingest_filter(body.model_dump(exclude_none=True), setting), _actor_user_id(claims),
            agent_config=await _agent_config(request, tenant, agent_id),
            recheck_worker=recheck)
    except SourceInactiveError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except WorkerUnavailable:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    await recheck()
    return {
        "source": _source_out(result["source"], scan_interval_minutes=svc.scan_interval_minutes),
        "opportunities": [_opportunity_out(o) for o in result["opportunities"]],
        "summary": {"created": result["created"], "updated": result["updated"],
                    "totalReturned": len(result["opportunities"])},
    }


def _parse_actions(actions: list[str] | None) -> list[str] | None:
    """Normalise the `actions` OR-filter query param. Supports both repeated `actions=` params and
    a single comma-separated value, trimming blanks. Returns None when nothing usable was given."""
    if not actions:
        return None
    parsed: list[str] = []
    for raw in actions:
        parsed.extend(part.strip() for part in (raw or "").split(",") if part.strip())
    return parsed or None


def _resolve_opportunity_limit(limit: str) -> int:
    """Turn the `limit` query param into a bounded row cap. Accepts `all` (or `0`/empty) for the
    unbounded "show everything" views, clamped to MAX_OPPORTUNITY_LIMIT to avoid abuse."""
    value = (limit or "").strip().lower()
    if value in ("", "all"):
        return MAX_OPPORTUNITY_LIMIT
    try:
        parsed = int(value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid limit") from e
    if parsed <= 0:
        return MAX_OPPORTUNITY_LIMIT
    return max(1, min(MAX_OPPORTUNITY_LIMIT, parsed))


@router.get("/{agent_id}/opportunities")
async def opportunities(agent_id: str, stage: str | None = None, recommendation: str | None = None,
                        source_key: str | None = None, title: str | None = None, search: str | None = None,
                        limit: str = "50", assigned_reviewer_user_id: str | None = None,
                        include_archived: bool = False, archived_only: bool = False,
                        tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    if stage and stage not in STAGES:
        raise HTTPException(status_code=422, detail="invalid stage")
    if recommendation and recommendation not in RECOMMENDATIONS:
        raise HTTPException(status_code=422, detail="invalid recommendation")
    resolved_limit = _resolve_opportunity_limit(limit)
    items = await svc.opportunities.list_for_agent(
        tenant, agent_id, stage=stage, recommendation=recommendation, source_key=source_key, title=title,
        search=search, assigned_reviewer_user_id=assigned_reviewer_user_id,
        include_archived=include_archived, archived_only=archived_only)
    items = items[:resolved_limit]
    return {"opportunities": [_opportunity_out(o) for o in items], "summary": await svc.dashboard_summary(tenant, agent_id)}


async def _get_opportunity_or_404(svc, tenant: str, agent_id: str, opportunity_id: str):
    o = await svc.opportunities.get(tenant, agent_id, opportunity_id)
    # Soft-deleted opportunities are gone as far as the API is concerned (parity with the list
    # endpoint, which already hides them), so a fetch/edit/delete after deletion 404s.
    if o is None or o.is_deleted():
        raise HTTPException(status_code=404, detail="opportunity not found")
    return o


@router.get("/{agent_id}/opportunities/{opportunity_id}")
async def opportunity(agent_id: str, opportunity_id: str, tenant: str = Depends(authed_tenant),
                      svc=Depends(get_sales_intel)) -> dict:
    from app.modules.sales_intelligence.detail import OpportunityDetailService

    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    return {"opportunity": _opportunity_out(o, detail_service=OpportunityDetailService())}


@router.get("/{agent_id}/opportunities/{opportunity_id}/history")
async def opportunity_history(agent_id: str, opportunity_id: str, limit: int = 100,
                              tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    logs = await svc.activity_logs.list_for_agent(tenant, agent_id, opportunity_id=opportunity_id,
                                                  limit=max(1, min(200, limit)))
    return {"opportunityId": opportunity_id, "history": [_log_out(log) for log in logs]}


class OpportunityContactBody(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class OpportunityLinkBody(BaseModel):
    url: str | None = None
    description: str | None = None


class CreateOpportunityBody(BaseModel):
    """Body for the manual "add an opportunity" flow (Ali's OpportunityCreateView). Everything is
    optional except `title`. Core fields map onto Opportunity columns; the richer descriptive fields
    (reference/notice_type/summaries/requirements/...) are persisted in raw_payload["manual"] and
    surfaced through the detail service, so no schema migration is needed."""
    title: str = Field(min_length=1, max_length=1024)
    buyer: str | None = None
    country: str | None = None
    region: str | None = None
    category: str | None = None
    estimated_value: float | None = None
    currency: str | None = None
    published_at: str | None = None
    deadline_at: str | None = None
    source_url: str | None = None
    source_key: str | None = None
    source_name: str | None = None
    stage: str | None = None
    run_qualification: bool = True
    # Enriched manual fields (Overview / Summary / Qualification / Notes tabs).
    reference: str | None = None
    notice_type: str | None = None
    security_clearance: str | None = None
    extraction_confidence: float | None = None
    framework: str | None = None
    contract_duration: str | None = None
    technology: str | None = None
    contacts: list[OpportunityContactBody] | None = None
    links: list[OpportunityLinkBody] | None = None
    executive_summary: str | None = None
    risk_summary: str | None = None
    opportunity_summary: str | None = None
    requirements: list[str] | None = None
    deliverables: list[str] | None = None
    qualification_score: int | None = None
    recommendation: str | None = None
    confidence: int | None = None
    ai_reasoning: str | None = None
    recommendations: list[str] | None = None
    notes: str | None = None


@router.post("/{agent_id}/opportunities", status_code=201)
async def create_opportunity(agent_id: str, body: CreateOpportunityBody, request: Request,
                             tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(require_role(Role.editor)),
                             mutation=Depends(get_sales_intel_mutation)) -> dict:
    if body.stage and body.stage not in STAGES:
        raise HTTPException(status_code=422, detail="invalid stage")
    data = body.model_dump(exclude={"run_qualification"}, exclude_none=True)
    for key in ("published_at", "deadline_at"):
        if data.get(key):
            from dateutil import parser as dateutil_parser

            data[key] = dateutil_parser.parse(data[key])
    o = await mutation.create_manual(tenant, agent_id, data, _actor_user_id(claims), body.run_qualification,
                                     agent_config=await _agent_config(request, tenant, agent_id))
    return {"opportunity": _opportunity_out(o)}


class UpdateOpportunityBody(BaseModel):
    """Body for editing a manual (or scanned) opportunity (Ali's OpportunityDetailView edit form).
    Every field is optional -- only the supplied ones are patched. Mirrors CreateOpportunityBody's
    enriched field set."""
    title: str | None = None
    buyer: str | None = None
    country: str | None = None
    region: str | None = None
    category: str | None = None
    estimated_value: float | None = None
    currency: str | None = None
    published_at: str | None = None
    deadline_at: str | None = None
    source_url: str | None = None
    requalify: bool = False
    # Enriched manual fields (Overview / Summary / Qualification / Notes tabs).
    reference: str | None = None
    notice_type: str | None = None
    security_clearance: str | None = None
    extraction_confidence: float | None = None
    framework: str | None = None
    contract_duration: str | None = None
    technology: str | None = None
    contacts: list[OpportunityContactBody] | None = None
    links: list[OpportunityLinkBody] | None = None
    executive_summary: str | None = None
    risk_summary: str | None = None
    opportunity_summary: str | None = None
    requirements: list[str] | None = None
    deliverables: list[str] | None = None
    qualification_score: int | None = None
    recommendation: str | None = None
    confidence: int | None = None
    ai_reasoning: str | None = None
    recommendations: list[str] | None = None
    notes: str | None = None


@router.patch("/{agent_id}/opportunities/{opportunity_id}")
async def update_opportunity(agent_id: str, opportunity_id: str, body: UpdateOpportunityBody, request: Request,
                             tenant: str = Depends(authed_tenant), claims: dict = Depends(require_role(Role.editor)),
                             svc=Depends(get_sales_intel), mutation=Depends(get_sales_intel_mutation)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    if o.is_archived():
        raise HTTPException(status_code=422, detail="Archived opportunities cannot be edited. Restore first.")
    if o.stage == "pushed" or o.salesforce_opportunity_id:
        raise HTTPException(status_code=422, detail="Pushed opportunities cannot be edited.")

    data = body.model_dump(exclude={"requalify"}, exclude_none=True)
    for key in ("published_at", "deadline_at"):
        if data.get(key):
            from dateutil import parser as dateutil_parser

            data[key] = dateutil_parser.parse(data[key])
    if not data and not body.requalify:
        raise HTTPException(status_code=422, detail="At least one editable field or requalify is required.")

    o = await mutation.update_fields(o, data, _actor_user_id(claims), body.requalify,
                                     agent_config=await _agent_config(request, tenant, agent_id))
    return {"opportunity": _opportunity_out(o)}


class TransitionBody(BaseModel):
    stage: str


@router.post("/{agent_id}/opportunities/{opportunity_id}/transition")
async def transition_opportunity(agent_id: str, opportunity_id: str, body: TransitionBody,
                                 tenant: str = Depends(authed_tenant),
                                 claims: dict = Depends(require_role(Role.editor)),
                                 svc=Depends(get_sales_intel)) -> dict:
    """Move an opportunity to a manual/pipeline stage (kanban drag, keyboard "Move to...", or the
    "Run Qualification" action which targets `qualifying`). The Salesforce-driven stages are not
    settable here: reaching `pushed` must go through the push-to-salesforce action."""
    if body.stage not in STAGES:
        raise HTTPException(status_code=422, detail="invalid stage")
    if body.stage not in MANUAL_TRANSITION_STAGES:
        raise HTTPException(status_code=422,
                            detail=f"stage '{body.stage}' cannot be set manually; use the relevant action instead.")
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    if o.is_archived():
        raise HTTPException(status_code=422, detail="Archived opportunities cannot be moved. Restore first.")
    if o.stage == "pushed" or o.salesforce_opportunity_id:
        raise HTTPException(status_code=422, detail="Pushed opportunities cannot be moved.")
    try:
        o = await svc.transition_stage(o, body.stage, _actor_user_id(claims))
    except InvalidStageTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"opportunity": _opportunity_out(o)}


@router.post("/{agent_id}/opportunities/{opportunity_id}/archive")
async def archive_opportunity(agent_id: str, opportunity_id: str, tenant: str = Depends(authed_tenant),
                              claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel),
                              mutation=Depends(get_sales_intel_mutation)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    o = await mutation.archive(o, _actor_user_id(claims))
    return {"opportunity": _opportunity_out(o)}


@router.post("/{agent_id}/opportunities/{opportunity_id}/restore")
async def restore_opportunity(agent_id: str, opportunity_id: str, tenant: str = Depends(authed_tenant),
                              claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel),
                              mutation=Depends(get_sales_intel_mutation)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    o = await mutation.restore(o, _actor_user_id(claims))
    return {"opportunity": _opportunity_out(o)}


@router.delete("/{agent_id}/opportunities/{opportunity_id}")
async def delete_opportunity(agent_id: str, opportunity_id: str, tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel),
                             mutation=Depends(get_sales_intel_mutation)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    o = await mutation.soft_delete(o, _actor_user_id(claims))
    return {"opportunity": _opportunity_out(o)}


@router.get("/{agent_id}/activity-logs")
async def activity_logs(agent_id: str, activity_type: str | None = None, action: str | None = None,
                        actions: list[str] | None = Query(default=None),
                        opportunity_id: str | None = None, limit: int = 50,
                        tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    if activity_type and activity_type not in ACTIVITY_TYPES:
        raise HTTPException(status_code=422, detail="invalid activity_type")
    # `actions` is an OR filter (repeated `actions=` params or a single comma-separated value) so
    # the Salesforce log can scope itself to just the Salesforce action set. `action` (singular)
    # stays for exact single-action lookups.
    action_list = _parse_actions(actions)
    logs = await svc.activity_logs.list_for_agent(tenant, agent_id, activity_type=activity_type, action=action,
                                                  actions=action_list, opportunity_id=opportunity_id,
                                                  limit=max(1, min(100, limit)))
    out = [_log_out(log) for log in logs]
    # FE (creator/lib/api.ts getSalesActivityLogs) reads `.logs`/`.total`; keep this response shape
    # aligned with that contract -- the salesforce-log page renders an empty table otherwise.
    return {"logs": out, "total": len(out)}


@router.get("/{agent_id}/scan-history")
async def scan_history(agent_id: str, source_key: str | None = None, status: str | None = None, limit: int = 50,
                       tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    logs = await svc.activity_logs.list_for_agent(tenant, agent_id, activity_type="source_scan",
                                                  limit=max(1, min(200, limit)))
    if source_key:
        logs = [log for log in logs
                if (log.metadata or {}).get("source_key") == source_key or log.action.startswith(f"{source_key}_scan_")]
    if status:
        suffix = "_scan_completed" if status == "success" else "_scan_failed"
        logs = [log for log in logs if log.action.endswith(suffix)]
    # FE (creator/lib/api.ts getSalesScanHistory) reads `.history`; keep the key aligned.
    return {"history": [_log_out(log) for log in logs]}


class ReviewBody(BaseModel):
    decision: str
    notes: str | None = None


@router.post("/{agent_id}/opportunities/{opportunity_id}/review")
async def review(agent_id: str, opportunity_id: str, body: ReviewBody, tenant: str = Depends(authed_tenant),
                 claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel)) -> dict:
    if body.decision not in REVIEW_DECISIONS:
        raise HTTPException(status_code=422, detail="invalid decision")
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    o = await svc.record_human_review(o, body.decision, body.notes, _actor_user_id(claims))
    return {"opportunity": _opportunity_out(o)}


class AssignReviewerBody(BaseModel):
    # Faithful to source (user_id), plus a free-text name fallback since the V2 teams module
    # isn't enumerable per-tenant yet. Both null == clear the reviewer.
    user_id: str | None = None
    name: str | None = None


@router.patch("/{agent_id}/opportunities/{opportunity_id}/assign-reviewer")
async def assign_reviewer(agent_id: str, opportunity_id: str, body: AssignReviewerBody,
                          tenant: str = Depends(authed_tenant), claims: dict = Depends(require_role(Role.editor)),
                          svc=Depends(get_sales_intel), mutation=Depends(get_sales_intel_mutation)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    o = await mutation.assign_reviewer(o, body.user_id, body.name, _actor_user_id(claims))
    return {"opportunity": _opportunity_out(o)}


@router.get("/{agent_id}/opportunities/{opportunity_id}/decisions")
async def opportunity_decisions(agent_id: str, opportunity_id: str, limit: int = 100,
                                tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    """Decision History -- the approve/reject/override audit trail for one opportunity, derived
    from the `human_review_recorded` activity logs (mirrors IdgSalesController::decisionHistory)."""
    await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    logs = await svc.activity_logs.list_for_agent(tenant, agent_id, opportunity_id=opportunity_id,
                                                  action="human_review_recorded", limit=max(1, min(200, limit)))
    return {"opportunityId": opportunity_id, "decisions": [_decision_out(log) for log in logs]}


# UI decision filter -> the stored decision value. "override" is the label for a needs_review
# decision; "all" (or an omitted param) applies no decision filter.
_DECISION_FILTERS = {"approved", "rejected", "needs_review", "override", "all"}
_DECISION_FILTER_ALIASES = {"override": "needs_review"}


@router.get("/{agent_id}/decision-history")
async def decision_history(agent_id: str, decision: str | None = None, reviewer_user_id: str | None = None,
                           limit: int = 200, tenant: str = Depends(authed_tenant),
                           svc=Depends(get_sales_intel)) -> dict:
    """Agent-level Decision History -- the approve/reject/override audit trail aggregated across ALL
    opportunities for this agent/tenant (mirrors Ali's IdgSalesController agent decision-history).
    Viewer-readable like the other read endpoints. Optional filters: `decision`
    (approved|rejected|needs_review|override|all) and `reviewer_user_id`."""
    if decision is not None and decision not in _DECISION_FILTERS:
        raise HTTPException(status_code=422, detail="invalid decision")
    decision_key = _DECISION_FILTER_ALIASES.get(decision or "all", decision or "all")

    logs = await svc.activity_logs.list_for_agent(tenant, agent_id, action="human_review_recorded",
                                                  limit=max(1, min(MAX_OPPORTUNITY_LIMIT, limit)))

    # Enrich each decision with its opportunity's title/stage and a best-effort reviewer name
    # (resolved from any opportunity where this user is the assigned reviewer -- V2 has no
    # tenant-wide user directory to look names up in).
    opportunities = await svc.opportunities.list_for_agent(tenant, agent_id, include_archived=True)
    opp_by_id = {o.id: o for o in opportunities}
    names_by_user: dict[str, str] = {}
    for o in opportunities:
        if o.assigned_reviewer_user_id and o.assigned_reviewer_name:
            names_by_user.setdefault(o.assigned_reviewer_user_id, o.assigned_reviewer_name)

    def _reviewer(user_id: str | None) -> dict | None:
        if user_id is None:
            return None
        return {"id": user_id, "userName": names_by_user.get(user_id), "email": None}

    # The reviewers dropdown is the full distinct set (independent of the current filters) so it
    # stays stable as the user filters. Preserve newest-first encounter order.
    reviewers: list[dict] = []
    seen: set[str] = set()
    for log in logs:
        uid = log.actor_user_id
        if uid is not None and uid not in seen:
            seen.add(uid)
            reviewers.append(_reviewer(uid))  # type: ignore[arg-type]

    entries: list[dict] = []
    for log in logs:
        record = _decision_out(log)
        if decision_key != "all" and record["decision"] != decision_key:
            continue
        if reviewer_user_id and record["reviewerUserId"] != reviewer_user_id:
            continue
        opp = opp_by_id.get(log.opportunity_id)
        record["opportunityTitle"] = opp.title if opp is not None else None
        record["opportunityStage"] = opp.stage if opp is not None else None
        record["reviewer"] = _reviewer(log.actor_user_id)
        entries.append(record)

    summary = {
        "approved": sum(1 for e in entries if e["decision"] == "approved"),
        "rejected": sum(1 for e in entries if e["decision"] == "rejected"),
        "overrides": sum(1 for e in entries if e["decision"] == "needs_review"),
        "total": len(entries),
    }
    return {"decisionHistory": entries, "reviewers": reviewers, "summary": summary}


class NotesBody(BaseModel):
    notes: str | None = None


@router.post("/{agent_id}/opportunities/{opportunity_id}/notes")
async def save_notes(agent_id: str, opportunity_id: str, body: NotesBody, tenant: str = Depends(authed_tenant),
                     claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    o = await svc.update_notes(o, body.notes, _actor_user_id(claims))
    return {"opportunity": _opportunity_out(o)}


@router.get("/{agent_id}/salesforce/status")
async def salesforce_status(agent_id: str, tenant: str = Depends(authed_tenant),
                            auth=Depends(get_salesforce_auth)) -> dict:
    connection = await auth.get_or_create_connection(tenant, agent_id)
    return {"salesforce": _salesforce_out(connection, auth)}


@router.post("/{agent_id}/salesforce/connect")
async def salesforce_connect(agent_id: str, request: Request,
                             tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(require_role(Role.editor)), auth=Depends(get_salesforce_auth)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    try:
        result = auth.build_authorize_url(tenant, agent_id, _actor_user_id(claims))
    except SalesforceNotConfiguredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await recheck()
    return {"authorizeUrl": result["authorizeUrl"], "state": result["state"], "oauthCallbackUrl": auth.redirect_uri()}


@router.get("/salesforce/oauth/callback")
async def salesforce_oauth_callback(request: Request, code: str | None = None, state: str | None = None,
                                    error: str | None = None, error_description: str | None = None,
                                    auth=Depends(get_salesforce_auth)):
    from app.core.config import get_settings

    s = get_settings()

    def _redirect(agent_id: str | None, err: str | None) -> RedirectResponse:
        path = s.salesforce_frontend_success_path.replace("{agentId}", agent_id or "")
        url = s.frontend_url.rstrip("/") + path
        params = {"salesforce": "error" if err else "connected"}
        if err:
            params["message"] = err
        from urllib.parse import urlencode

        sep = "&" if "?" in url else "?"
        return RedirectResponse(url=f"{url}{sep}{urlencode(params)}")

    if error:
        return _redirect(None, error_description or error)
    if not code or not state:
        return _redirect(None, "Missing Salesforce OAuth code or state.")
    async def recheck(tenant: str, agent_id: str) -> None:
        await require_available_worker(
            agents=request.app.state.agents, tenant=tenant, agent_id=agent_id)

    try:
        result = await auth.handle_callback(code, state, recheck_worker=recheck)
    except Exception as e:
        return _redirect(None, str(e))
    return _redirect(result.get("agent_id"), None)


@router.post("/{agent_id}/salesforce/disconnect")
async def salesforce_disconnect(agent_id: str, request: Request,
                                tenant: str = Depends(authed_tenant),
                                claims: dict = Depends(require_role(Role.editor)), auth=Depends(get_salesforce_auth)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    connection = await auth.disconnect(tenant, agent_id, _actor_user_id(claims))
    await recheck()
    return {"salesforce": _salesforce_out(connection, auth)}


@router.post("/{agent_id}/opportunities/{opportunity_id}/push-to-salesforce")
async def push_to_salesforce(agent_id: str, opportunity_id: str, request: Request,
                             tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel),
                             push=Depends(get_salesforce_push)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    try:
        pushed = await push.push(o, _actor_user_id(claims), recheck_worker=recheck)
    except SalesforceError as e:
        msg = str(e).lower()
        status_code = 422 if ("not connected" in msg or "validated" in msg) else 502
        raise HTTPException(status_code=status_code, detail=str(e)) from e
    await recheck()
    return {"opportunity": _opportunity_out(pushed)}
