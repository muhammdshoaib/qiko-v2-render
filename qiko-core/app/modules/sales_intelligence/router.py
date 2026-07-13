"""IDG Sales Intelligence HTTP API -- tenant-scoped equivalent of
app/Http/Controllers/Api/IdgSales/IdgSalesController.php.

Route shape follows qiko-core's existing per-agent module convention (see app.modules.crm.router):
`/sales-intelligence/{agent_id}/...` under the `/api/v1` prefix, instead of the Laravel branch's
`/api/avatar/idg-sales/{agentId}/...`. All endpoints are tenant-scoped via `authed_tenant`
(BOLA-safe -- tenant comes from the verified access-token claims, never a client-supplied header).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, require_role
from app.modules.identity.rbac import Role
from app.modules.sales_intelligence.models import (
    ACTIVITY_TYPES,
    RECOMMENDATIONS,
    REVIEW_DECISIONS,
    SOURCE_KEYS,
    SOURCE_STATUSES,
    STAGES,
)
from app.modules.sales_intelligence.salesforce import SalesforceError, SalesforceNotConfiguredError
from app.modules.sales_intelligence.service import SourceInactiveError

router = APIRouter(prefix="/sales-intelligence", tags=["sales-intelligence"])


def get_sales_intel(request: Request):
    return request.app.state.sales_intel


def get_sales_intel_mutation(request: Request):
    return request.app.state.sales_intel_mutation


def get_salesforce_auth(request: Request):
    return request.app.state.salesforce_auth


def get_salesforce_push(request: Request):
    return request.app.state.salesforce_push


def _actor_user_id(claims: dict) -> str | None:
    return claims.get("sub") or claims.get("user_id")


def _source_out(s) -> dict:
    return {
        "id": s.id, "agentId": s.agent_id, "sourceKey": s.source_key, "name": s.name, "type": s.type,
        "status": s.status, "authStatus": s.auth_status, "scanCadence": s.scan_cadence,
        "lastScanStatus": s.last_scan_status, "lastScanAt": s.last_scan_at, "opportunitiesFound": s.opportunities_found,
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
        "humanReviewNotes": o.human_review_notes, "reviewedAt": o.reviewed_at, "archivedAt": o.archived_at,
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
    return {"sources": [_source_out(s) for s in items]}


class UpdateSourceBody(BaseModel):
    status: str


@router.patch("/{agent_id}/sources/{source_key}")
async def update_source(agent_id: str, source_key: str, body: UpdateSourceBody,
                        tenant: str = Depends(authed_tenant), claims: dict = Depends(require_role(Role.editor)),
                        svc=Depends(get_sales_intel)) -> dict:
    if source_key not in SOURCE_KEYS or body.status not in SOURCE_STATUSES:
        raise HTTPException(status_code=422, detail="invalid source_key or status")
    source = await svc.update_source_status(tenant, agent_id, source_key, body.status, _actor_user_id(claims))
    return {"source": _source_out(source)}


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
async def scan_ungm(agent_id: str, body: ScanBody, tenant: str = Depends(authed_tenant),
                    claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel)) -> dict:
    try:
        result = await svc.scan_ungm(tenant, agent_id, body.model_dump(exclude_none=True), _actor_user_id(claims))
    except SourceInactiveError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "source": _source_out(result["source"]),
        "opportunities": [_opportunity_out(o) for o in result["opportunities"]],
        "summary": {"created": result["created"], "updated": result["updated"],
                    "totalReturned": len(result["opportunities"])},
    }


@router.post("/{agent_id}/scan/ted")
async def scan_ted(agent_id: str, body: ScanBody, tenant: str = Depends(authed_tenant),
                   claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel)) -> dict:
    try:
        result = await svc.scan_ted(tenant, agent_id, body.model_dump(exclude_none=True), _actor_user_id(claims))
    except SourceInactiveError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "source": _source_out(result["source"]),
        "opportunities": [_opportunity_out(o) for o in result["opportunities"]],
        "summary": {"created": result["created"], "updated": result["updated"],
                    "totalReturned": len(result["opportunities"])},
    }


@router.get("/{agent_id}/opportunities")
async def opportunities(agent_id: str, stage: str | None = None, recommendation: str | None = None,
                        source_key: str | None = None, title: str | None = None, search: str | None = None,
                        limit: int = 50, include_archived: bool = False, archived_only: bool = False,
                        tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    if stage and stage not in STAGES:
        raise HTTPException(status_code=422, detail="invalid stage")
    if recommendation and recommendation not in RECOMMENDATIONS:
        raise HTTPException(status_code=422, detail="invalid recommendation")
    items = await svc.opportunities.list_for_agent(
        tenant, agent_id, stage=stage, recommendation=recommendation, source_key=source_key, title=title,
        search=search, include_archived=include_archived, archived_only=archived_only)
    items = items[: max(1, min(100, limit))]
    return {"opportunities": [_opportunity_out(o) for o in items], "summary": await svc.dashboard_summary(tenant, agent_id)}


async def _get_opportunity_or_404(svc, tenant: str, agent_id: str, opportunity_id: str):
    o = await svc.opportunities.get(tenant, agent_id, opportunity_id)
    if o is None:
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


class CreateOpportunityBody(BaseModel):
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


@router.post("/{agent_id}/opportunities", status_code=201)
async def create_opportunity(agent_id: str, body: CreateOpportunityBody, tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(require_role(Role.editor)),
                             mutation=Depends(get_sales_intel_mutation)) -> dict:
    if body.stage and body.stage not in STAGES:
        raise HTTPException(status_code=422, detail="invalid stage")
    data = body.model_dump(exclude={"run_qualification"}, exclude_none=True)
    for key in ("published_at", "deadline_at"):
        if data.get(key):
            from dateutil import parser as dateutil_parser

            data[key] = dateutil_parser.parse(data[key])
    o = await mutation.create_manual(tenant, agent_id, data, _actor_user_id(claims), body.run_qualification)
    return {"opportunity": _opportunity_out(o)}


class UpdateOpportunityBody(BaseModel):
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


@router.patch("/{agent_id}/opportunities/{opportunity_id}")
async def update_opportunity(agent_id: str, opportunity_id: str, body: UpdateOpportunityBody,
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

    o = await mutation.update_fields(o, data, _actor_user_id(claims), body.requalify)
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
                             claims: dict = Depends(require_role(Role.owner)), svc=Depends(get_sales_intel),
                             mutation=Depends(get_sales_intel_mutation)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    o = await mutation.soft_delete(o, _actor_user_id(claims))
    return {"opportunity": _opportunity_out(o)}


@router.get("/{agent_id}/activity-logs")
async def activity_logs(agent_id: str, activity_type: str | None = None, action: str | None = None,
                        opportunity_id: str | None = None, limit: int = 50,
                        tenant: str = Depends(authed_tenant), svc=Depends(get_sales_intel)) -> dict:
    if activity_type and activity_type not in ACTIVITY_TYPES:
        raise HTTPException(status_code=422, detail="invalid activity_type")
    logs = await svc.activity_logs.list_for_agent(tenant, agent_id, activity_type=activity_type, action=action,
                                                  opportunity_id=opportunity_id, limit=max(1, min(100, limit)))
    return {"activityLogs": [_log_out(log) for log in logs]}


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
    return {"scanHistory": [_log_out(log) for log in logs]}


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
async def salesforce_connect(agent_id: str, tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(require_role(Role.editor)), auth=Depends(get_salesforce_auth)) -> dict:
    try:
        result = auth.build_authorize_url(tenant, agent_id, _actor_user_id(claims))
    except SalesforceNotConfiguredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
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
    try:
        result = await auth.handle_callback(code, state)
    except Exception as e:
        return _redirect(None, str(e))
    return _redirect(result.get("agent_id"), None)


@router.post("/{agent_id}/salesforce/disconnect")
async def salesforce_disconnect(agent_id: str, tenant: str = Depends(authed_tenant),
                                claims: dict = Depends(require_role(Role.editor)), auth=Depends(get_salesforce_auth)) -> dict:
    connection = await auth.disconnect(tenant, agent_id, _actor_user_id(claims))
    return {"salesforce": _salesforce_out(connection, auth)}


@router.post("/{agent_id}/opportunities/{opportunity_id}/push-to-salesforce")
async def push_to_salesforce(agent_id: str, opportunity_id: str, tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(require_role(Role.editor)), svc=Depends(get_sales_intel),
                             push=Depends(get_salesforce_push)) -> dict:
    o = await _get_opportunity_or_404(svc, tenant, agent_id, opportunity_id)
    try:
        pushed = await push.push(o, _actor_user_id(claims))
    except SalesforceError as e:
        msg = str(e).lower()
        status_code = 422 if ("not connected" in msg or "validated" in msg) else 502
        raise HTTPException(status_code=status_code, detail=str(e)) from e
    return {"opportunity": _opportunity_out(pushed)}
