"""Admin HTTP API (tenant-scoped). Revenue computed from a single source (the posted subs)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app import __version__ as app_version
from app.core.config import get_settings
from app.core.deps import (
    get_user_store,
    require_platform_capability,
    require_platform_identity,
    authed_tenant,
    current_claims,
)
from app.modules.ai.caps import PLATFORM, UNLIMITED, CostCap
from app.modules.audit import registry as audit_actions
from app.modules.audit import retention as audit_retention
from app.modules.audit import service as audit
from app.modules.admin.metrics import Subscription, revenue_metrics
from app.modules.health.system import (
    database_stats,
    process_stats,
    queue_stats,
    readiness,
    redis_stats,
)
from app.modules.admin.pagination import MAX_PAGE_SIZE, PAGE_SIZE, paginate
from app.modules.admin.sorting import (
    MONITORING_SORTS,
    TENANT_SORTS,
    USER_SORTS,
    WORKER_SORTS,
    apply_sort,
)
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import AdminRole, Capability
from app.modules.agents.service import AGENT_STATUSES
from app.modules.identity.rbac import Role
from app.modules.identity.team_access import ASSIGNABLE_ROLES
from app.modules.identity.team_access import ROLE_LABELS

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


class AdminSelfOut(BaseModel):
    role: AdminRole
    # The effective capability set, so the admin UI can hide what the caller cannot do instead of
    # letting them click into a 403.
    capabilities: list[str] = []


class AdminWorkerOut(BaseModel):
    id: str
    name: str
    type: str
    status: str
    enabled: bool
    created_at: datetime
    config: dict[str, str | bool | int | float]


class WorkerStateAuditOut(BaseModel):
    id: int
    agent_id: str
    changed_by_email: str
    previous_enabled: bool
    enabled: bool
    reason: str | None
    created_at: datetime


class CustomerDetailOut(BaseModel):
    user_id: str
    email: str
    plan: str
    earnings_cents: int
    is_studio: bool
    deleted: bool
    workers: list[AdminWorkerOut]
    worker_state_audit: list[WorkerStateAuditOut]


class SubscriptionIn(BaseModel):
    customer_id: str
    plan: str
    price_cents: int
    interval: str = "month"
    status: str = "active"


@router.post("/revenue")
def revenue(subs: list[SubscriptionIn], _tenant: str = Depends(authed_tenant),
            _identity=Depends(require_platform_capability(Capability.view_customers))) -> dict:
    return revenue_metrics([Subscription(**s.model_dump()) for s in subs])


@router.get("/customers")
def customers(request: Request, _tenant: str = Depends(authed_tenant),
              _identity=Depends(require_platform_capability(Capability.view_customers)),
              search: str | None = Query(default=None, max_length=200),
              plan: str | None = Query(default=None, max_length=40),
              sort: str | None = Query(default=None, max_length=32),
              order: str = Query(default="desc", pattern="^(asc|desc)$"),
              page: int = Query(default=1, ge=1),
              page_size: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)) -> dict:
    directory = request.app.state.customers
    result = directory.list(search=search, plan=plan, page=page, page_size=page_size,
                            sort=sort, order=order)
    return {"total": result["total"], "page": result["page"], "page_size": page_size,
            "items": [{"user_id": r.user_id, "email": r.email, "plan": r.plan,
                       "earnings_cents": r.earnings_cents} for r in result["items"]]}


def _customer_json(record) -> dict:
    return {"user_id": record.user_id, "email": record.email, "plan": record.plan,
            "earnings_cents": record.earnings_cents, "is_studio": record.is_studio,
            "deleted": record.deleted}


_ADMIN_CONFIG_DISPLAY_FIELDS = frozenset({
    "archived", "expertise", "industry", "language", "tone",
    "vapi_credentials_added", "calendly_is_linked", "salesforce_credentials_added",
    "calendly_credentials_added", "clickup_credentials_added", "slack_credentials_added",
    "gmail_credentials_added",
})


def _safe_agent_config(config: dict) -> dict:
    return {
        key: value for key, value in config.items()
        if key in _ADMIN_CONFIG_DISPLAY_FIELDS and isinstance(value, (str, bool, int, float))
    }


def _worker_json(agent) -> dict:
    return {
        "id": agent.id, "name": agent.name, "type": agent.atype, "status": agent.status,
        "enabled": agent.enabled, "created_at": agent.created_at,
        "config": _safe_agent_config(agent.config),
    }


def _audit_json(entry) -> dict:
    return {
        "id": entry.id, "agent_id": entry.agent_id,
        "changed_by_email": entry.changed_by_email,
        "previous_enabled": entry.previous_enabled, "enabled": entry.enabled,
        "reason": entry.reason, "created_at": entry.created_at,
    }


@router.get("/me", response_model=AdminSelfOut)
async def admin_me(_tenant: str = Depends(authed_tenant),
                   identity=Depends(require_platform_identity())) -> dict:
    return {"role": identity.role.value,
            "capabilities": sorted(c.value for c in identity.capabilities)}


@router.get("/customers/{user_id}", response_model=CustomerDetailOut)
async def customer_detail(user_id: str, request: Request,
                          _tenant: str = Depends(authed_tenant),
                          _identity=Depends(require_platform_capability(Capability.view_customers))) -> dict:
    record = await run_in_threadpool(request.app.state.customers.details, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="customer not found")
    workers = await request.app.state.agents.list(user_id)
    audit = await request.app.state.agents.list_state_audit(user_id, limit=50)
    return {
        **_customer_json(record),
        "workers": [_worker_json(worker) for worker in workers],
        "worker_state_audit": [_audit_json(entry) for entry in audit],
    }


class WorkerEnabledBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    reason: str | None = Field(default=None, max_length=1000)


_CSRF_OPENAPI = {
    "parameters": [
        {
            "name": "X-CSRF-Token", "in": "header", "required": True,
            "schema": {"type": "string"},
            "description": "Must match the qiko_csrf cookie.",
        },
        {
            "name": "qiko_csrf", "in": "cookie", "required": True,
            "schema": {"type": "string"},
            "description": "Double-submit CSRF cookie.",
        },
    ]
}


def _require_csrf(request: Request) -> None:
    csrf.require_csrf(request)


@router.patch(
    "/customers/{customer_id}/workers/{agent_id}/enabled",
    response_model=AdminWorkerOut,
    openapi_extra=_CSRF_OPENAPI,
)
async def set_worker_enabled(customer_id: str, agent_id: str, body: WorkerEnabledBody,
                             request: Request, _tenant: str = Depends(authed_tenant),
                             claims: dict = Depends(current_claims),
                             _identity=Depends(require_platform_capability(Capability.manage_workers))) -> dict:
    if await run_in_threadpool(request.app.state.customers.details, customer_id) is None:
        raise HTTPException(status_code=404, detail="worker not found")
    agent = await request.app.state.agents.get(customer_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="worker not found")
    _require_csrf(request)
    changed = await request.app.state.agents.set_enabled(
        customer_id, agent_id, body.enabled,
        changed_by_email=str(claims["email"]), reason=body.reason)
    return _worker_json(changed)


class StudioBody(BaseModel):
    enabled: bool


@router.post("/customers/{user_id}/studio", openapi_extra=_CSRF_OPENAPI)
async def customer_studio(user_id: str, body: StudioBody, request: Request,
                          claims: dict = Depends(current_claims),
                          _tenant: str = Depends(authed_tenant),
                          _identity=Depends(require_platform_capability(Capability.manage_customers))) -> dict:
    before = await run_in_threadpool(request.app.state.customers.details, user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _require_csrf(request)
    try:
        record = await run_in_threadpool(
            request.app.state.customers.set_studio, user_id, body.enabled
        )
        # Previously the only trace was admin_customer_flags.updated_at, with no actor at all.
        await audit.record(request.app.state.audit, audit.AuditEvent(
            action=audit_actions.STUDIO_TOGGLED, target_id=user_id, target_label=before.email,
            tenant_id=user_id, actor_type=audit.PLATFORM_ADMIN,
            actor_id=str(claims.get("email") or ""), actor_label=str(claims.get("email") or ""),
            changes=audit.diff(audit_actions.STUDIO_TOGGLED,
                               {"is_studio": bool(before.is_studio)},
                               {"is_studio": bool(body.enabled)})), request=request)
        return _customer_json(record)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="customer not found") from exc


@router.delete("/customers/{user_id}", openapi_extra=_CSRF_OPENAPI)
async def customer_delete(user_id: str, request: Request,
                          claims: dict = Depends(current_claims),
                          _tenant: str = Depends(authed_tenant),
                          _identity=Depends(require_platform_capability(Capability.manage_customers))) -> dict:
    before = await run_in_threadpool(request.app.state.customers.details, user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _require_csrf(request)
    try:
        record = await run_in_threadpool(request.app.state.customers.soft_delete, user_id)
        # This hides a tenant platform-wide, anonymises its email and has no reversal endpoint, and it
        # recorded nothing at all: not who did it, not when, not why.
        # NOT the email. Soft delete exists to anonymise it, so copying it into a table an operator
        # can read would undo the erasure it was performing.
        await audit.record(request.app.state.audit, audit.AuditEvent(
            action=audit_actions.CUSTOMER_SOFT_DELETED, target_id=user_id, tenant_id=user_id,
            actor_type=audit.PLATFORM_ADMIN, actor_id=str(claims.get("email") or ""),
            actor_label=str(claims.get("email") or ""),
            # A header, not the query string: an operator reason in a URL is written verbatim into
            # edge access logs, which sit outside this store's retention and erasure path.
            reason=request.headers.get("x-audit-reason"),
            changes=audit.diff(audit_actions.CUSTOMER_SOFT_DELETED,
                               {"state": "active"}, {"state": "deleted"})), request=request)
        return _customer_json(record)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="customer not found") from exc


@router.get("/overview")
def overview(request: Request, _tenant: str = Depends(authed_tenant),
             _identity=Depends(require_platform_capability(Capability.view_customers))) -> dict:
    subs = request.app.state.subscriptions.summary()
    customers_total = request.app.state.customers.list()["total"]
    return {"customers_total": customers_total, **subs}


@router.get("/analytics")
def analytics(request: Request, _tenant: str = Depends(authed_tenant),
              _identity=Depends(require_platform_capability(Capability.view_customers)),
              start: str = "2026-01-01", end: str = "2026-12-31",
              fallback_start: str = "2020-01-01") -> dict:
    from app.modules.admin.ga4 import GA4Analytics

    empty = {"sessions": 0, "active_users": 0, "top_pages": [], "had_data": False}
    try:
        return GA4Analytics(request.app.state.ga4).dashboard(start, end, fallback_start=fallback_start)
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
        logger.warning("admin analytics unavailable: %s", exc)
    except Exception as exc:
        logger.exception("admin analytics failed: %s", exc)
    return empty


class TenantDirectoryRow(BaseModel):
    tenant_id: str
    email: str
    plan: str
    earnings_cents: int
    user_count: int
    worker_count: int
    is_studio: bool


@router.get("/tenants")
def tenants(request: Request, _tenant: str = Depends(authed_tenant),
            _identity=Depends(require_platform_capability(Capability.view_customers)),
            search: str | None = Query(default=None, max_length=200),
            plan: str | None = Query(default=None, max_length=40),
            sort: str | None = Query(default=None, max_length=32),
            order: str = Query(default="desc", pattern="^(asc|desc)$"),
            page: int = Query(default=1, ge=1),
            page_size: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)) -> dict:
    """The tenant directory (QIK-515).

    A "customer" already IS a tenant in this codebase, so this is the same rows as /admin/customers
    with the counts the console needs and never had: how many people are on the account and how many
    workers it runs. Both were already derivable and simply not surfaced.
    """
    result = request.app.state.customers.list(search=search, plan=plan, page=page,
                                              page_size=page_size, sort=sort, order=order,
                                              sort_spec=TENANT_SORTS)
    return {"total": result["total"], "page": result["page"], "page_size": page_size, "items": [{
        "tenant_id": record.user_id, "email": record.email, "plan": record.plan,
        "earnings_cents": record.earnings_cents, "user_count": record.users,
        "worker_count": record.agents, "is_studio": record.is_studio,
    } for record in result["items"]]}


def _user_directory_json(user, platform: dict, *, show_authority: bool) -> dict:
    key = user.email.lower()
    admin = platform.get(key)
    return {
        "id": user.id, "email": user.email, "name": user.name, "tenant_id": user.tenant,
        "role": user.role.value, "role_label": ROLE_LABELS.get(user.role, user.role.value),
        "twofa_enabled": user.twofa_enabled,
        # Membership is visible to any platform admin (GET /admin/org/role/{email} already tells them
        # that much); the ROLE and CAPABILITY SET are not.
        "is_platform_admin": admin is not None,
        "platform_role": admin.role.value if admin and show_authority else None,
        "platform_capabilities": sorted(c.value for c in admin.capabilities)
        if admin and show_authority else [],
    }


class UserDirectoryRow(BaseModel):
    id: str
    email: str
    name: str | None
    tenant_id: str | None
    role: str
    role_label: str
    twofa_enabled: bool
    is_platform_admin: bool
    platform_role: str | None
    platform_capabilities: list[str]


@router.get("/users")
async def users(request: Request, _tenant: str = Depends(authed_tenant),
                identity=Depends(require_platform_capability(Capability.view_customers)),
                search: str | None = Query(default=None, max_length=200),
                tenant_id: str | None = Query(default=None, max_length=64),
                role: str | None = Query(default=None, max_length=32),
                # "Who has not turned on 2FA" is the question an operator actually asks of a user
                # directory, and it could not be asked at all before.
                twofa: bool | None = None,
                platform_admins_only: bool = False,
                sort: str | None = Query(default=None, max_length=32),
                order: str = Query(default="asc", pattern="^(asc|desc)$"),
                page: int = Query(default=1, ge=1),
                page_size: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)) -> dict:
    """The site-wide user directory, annotated with platform access where a user also holds it.

    Two independent role systems exist: the TENANT role lives on users.role, while platform-admin
    access is keyed by EMAIL in platform_admins with no foreign key between them. This lists users and
    marks which of them also hold platform access. It is deliberately NOT the answer to "who has
    platform access" -- an operator provisioned by scripts/provision_platform_admin.py who never
    signed up has no user row and so appears nowhere here. GET /admin/org is that answer.

    The SCOPE of someone's platform authority is shown only to a caller holding manage_admins.
    QIK-513 put GET /admin/org behind that capability precisely so a read-only viewer cannot enumerate
    who holds manage_admins, which is the privilege-escalation root; leaking the same set through a
    weaker gate here would have undone that decision.

    No password hash, TOTP secret or session id is exposed: the fields are listed explicitly, and the
    store returns a projection that never loads them.
    """
    # Only a manage_admins holder sees the scope of platform authority.
    show_authority = identity is not None and identity.can(Capability.manage_admins)
    store = get_user_store()
    everyone = await store.list_all()
    platform = {admin.email: admin for admin in await request.app.state.admin_org.list_admins()}

    rows = everyone
    if tenant_id:
        rows = [user for user in rows if user.tenant == tenant_id]
    if search:
        needle = search.lower()
        rows = [user for user in rows
                if needle in user.email.lower() or needle in (user.name or "").lower()]
    rows = sorted(rows, key=lambda user: user.email)

    if role:
        rows = [user for user in rows if user.role.value == role]
    if twofa is not None:
        rows = [user for user in rows if bool(user.twofa_enabled) is twofa]
    if platform_admins_only:
        rows = [user for user in rows if user.email.lower() in platform]

    items = [_user_directory_json(user, platform, show_authority=show_authority) for user in rows]
    items = apply_sort(items, USER_SORTS, sort, order)
    result = paginate(items, page=page, page_size=page_size)
    return {"total": result["total"], "page": result["page"], "page_size": page_size,
            "items": result["items"]}


class WorkerDirectoryRow(AdminWorkerOut):
    tenant_id: str


@router.get("/workers")
async def workers(request: Request, _tenant: str = Depends(authed_tenant),
                  _identity=Depends(require_platform_capability(Capability.view_customers)),
                  search: str | None = Query(default=None, max_length=200),
                  tenant_id: str | None = Query(default=None, max_length=64),
                  enabled: bool | None = None,
                  status: str | None = Query(default=None, max_length=32),
                  sort: str | None = Query(default=None, max_length=32),
                  order: str = Query(default="asc", pattern="^(asc|desc)$"),
                  page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)) -> dict:
    """The cross-tenant worker directory (QIK-520).

    The enable/disable enforcement already exists per customer, but there was no way to see every
    worker on the platform at once, so answering "which workers are disabled right now" meant opening
    customers one by one. Config goes through the same allowlist as the customer detail view, so no
    secret key can leak into a directory listing.
    """
    everyone = await request.app.state.agents.list_all()

    rows = everyone
    if tenant_id:
        rows = [agent for agent in rows if agent.tenant == tenant_id]
    if enabled is not None:
        rows = [agent for agent in rows if agent.enabled is enabled]
    if search:
        needle = search.lower()
        rows = [agent for agent in rows
                if needle in agent.name.lower() or needle in agent.id.lower()]

    if status:
        rows = [agent for agent in rows if agent.status == status]

    items = [{**_worker_json(agent), "tenant_id": agent.tenant} for agent in rows]
    items = apply_sort(items, WORKER_SORTS, sort, order)
    result = paginate(items, page=page, page_size=page_size)
    return {"total": result["total"], "page": result["page"], "page_size": page_size,
            "items": result["items"]}


_MAX_WINDOW_DAYS = 400


def _window(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days), end


def _totals_json(totals) -> dict:
    return {"calls": totals.calls, "input_tokens": totals.input_tokens,
            "output_tokens": totals.output_tokens, "cost_nano_usd": totals.cost_nano_usd,
            # Surfaced so an operator can see when a total understates reality because a model has no
            # published rate yet, rather than trusting a plausible-looking number.
            "unpriced_calls": totals.unpriced_calls}


@router.get("/ai-cost")
async def ai_cost(request: Request, _tenant: str = Depends(authed_tenant),
                  _identity=Depends(require_platform_capability(Capability.view_ai_cost)),
                  days: int = Query(default=30, ge=1, le=_MAX_WINDOW_DAYS)) -> dict:
    """Platform AI spend, broken down by tenant, model, operation and day (QIK-517).

    Reads the events recorded by QIK-514. Cost is nano-USD because a single Titan embedding rounds to
    zero in micro-USD, and an ingest performs one per chunk.

    Gated on view_ai_cost rather than view_customers: per-account model spend reveals unit economics,
    which is sensitive in a different way from a customer list.
    """
    start, end = _window(days)
    store = request.app.state.ai_usage
    totals = await store.platform_totals(start=start, end=end)
    breakdowns = {name: {key: _totals_json(value) for key, value in
                         (await store.platform_by(name, start=start, end=end)).items()}
                  for name in ("tenant", "model", "operation", "day")}
    return {"window_days": days, "totals": _totals_json(totals), **breakdowns}


@router.get("/worker-monitoring")
async def worker_monitoring(request: Request, _tenant: str = Depends(authed_tenant),
                            identity=Depends(require_platform_capability(Capability.view_customers)),
                            days: int = Query(default=30, ge=1, le=_MAX_WINDOW_DAYS),
                            tenant_id: str | None = Query(default=None, max_length=64),
                            # The monitoring view had no search at all, so finding one worker among
                            # hundreds meant paging until it appeared.
                            search: str | None = Query(default=None, max_length=200),
                            enabled: bool | None = None,
                            sort: str | None = Query(default=None, max_length=32),
                            order: str = Query(default="desc", pattern="^(asc|desc)$"),
                            page: int = Query(default=1, ge=1),
                            page_size: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)) -> dict:
    """Every worker with its state and recent activity (QIK-521).

    Answers "is this worker alive and being used", which previously required opening each customer and
    inferring it from nothing. last_seen comes from the AI usage events, so it reflects real model
    activity rather than a heartbeat that would keep ticking for an idle worker.

    Visible to view_customers because worker state is operational, but the COST columns are returned
    only to a view_ai_cost holder. Ungating spend here would have made this endpoint a way around the
    /admin/ai-cost gate, which is the mistake QIK-515/516 made with platform authority.
    """
    show_cost = identity is not None and identity.can(Capability.view_ai_cost)
    start, end = _window(days)
    agents = await request.app.state.agents.list_all()
    if tenant_id:
        agents = [agent for agent in agents if agent.tenant == tenant_id]
    usage_by_agent = await request.app.state.ai_usage.platform_agent_usage(start=start, end=end)

    rows = []
    for agent in agents:
        summary = usage_by_agent.get(f"{agent.tenant}/{agent.id}")
        row = {
            "tenant_id": agent.tenant, "id": agent.id, "name": agent.name,
            "status": agent.status, "enabled": agent.enabled,
            "created_at": agent.created_at,
            "calls": summary.totals.calls if summary else 0,
            "last_seen": summary.last_seen if summary else None,
        }
        if show_cost:
            row["cost_nano_usd"] = summary.totals.cost_nano_usd if summary else 0
            row["input_tokens"] = summary.totals.input_tokens if summary else 0
            row["output_tokens"] = summary.totals.output_tokens if summary else 0
        rows.append(row)

    if search:
        needle = search.lower()
        rows = [row for row in rows
                if needle in (row["name"] or "").lower() or needle in row["id"].lower()]
    if enabled is not None:
        rows = [row for row in rows if row["enabled"] is enabled]
    # Busiest first by default: an operator opening this page is looking for the outliers, not an
    # alphabet. An explicit sort overrides it.
    rows.sort(key=lambda row: (-row["calls"], row["tenant_id"] or "", row["id"]))
    rows = apply_sort(rows, MONITORING_SORTS, sort, order)
    result = paginate(rows, page=page, page_size=page_size)
    return {"total": result["total"], "page": result["page"], "page_size": page_size,
            "window_days": days, "cost_visible": show_cost, "items": result["items"]}


@router.get("/system")
async def system(request: Request, _tenant: str = Depends(authed_tenant),
                 _identity=Depends(require_platform_capability(Capability.view_system_stats))) -> dict:
    """Infrastructure health and capacity (QIK-518).

    Answers the questions an operator currently answers by opening a shell on the host: are the
    dependencies actually up, how close is the database to its connection limit, is Redis evicting
    keys, and is the background queue draining.

    Every section degrades to available=false with a reason rather than raising, because a statistics
    dashboard that 500s when one collector fails is a dashboard that gets ignored precisely when it
    matters. Reasons are exception class names, never driver messages, which can carry a connection
    string.

    Gated on view_system_stats rather than view_customers: connection headroom and queue depth are
    operational reconnaissance, a different category from a customer list.
    """
    state = request.app.state
    ready, probes = await readiness(state)
    # return_exceptions so a collector that raises instead of degrading cannot 500 the dashboard.
    # Each collector already catches internally, but relying on all of them to keep remembering that
    # makes the promise above a convention rather than a guarantee.
    database, redis_info, queue = [
        result if not isinstance(result, BaseException)
        else {"available": False, "reason": type(result).__name__}
        for result in await asyncio.gather(
            database_stats(getattr(state, "sessionmaker", None)),
            redis_stats(getattr(state, "redis", None)),
            queue_stats(getattr(state, "redis", None)),
            return_exceptions=True,
        )
    ]
    settings = get_settings()
    return {
        "ready": ready,
        "checks": [probe.as_dict() for probe in probes],
        "process": process_stats(),
        "database": database,
        "redis": redis_info,
        "queue": queue,
        "environment": settings.environment.value,
        "version": app_version,
    }


class CostCapBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Negative means explicitly unlimited; 0 blocks. See app/modules/ai/caps.py for why the absence
    # of a row cannot express "unlimited and I meant it".
    monthly_cap_usd: float = Field(ge=-1)
    alert_threshold_pct: int = Field(default=80, ge=1, le=100)


def _cap_json(cap) -> dict:
    return {"tenant_id": cap.tenant, "agent_id": cap.agent_id,
            "monthly_cap_nano_usd": cap.monthly_cap_nano_usd,
            "unlimited": cap.unlimited,
            "alert_threshold_pct": cap.alert_threshold_pct,
            "updated_by_email": cap.updated_by_email,
            "updated_at": cap.updated_at.isoformat()}


@router.get("/cost-caps")
async def cost_caps(request: Request, _tenant: str = Depends(authed_tenant),
                    _identity=Depends(require_platform_capability(Capability.view_ai_cost))) -> dict:
    """Every configured cap. Readable with view_ai_cost, since a cap is part of the spend picture."""
    caps = await request.app.state.cost_caps.list_all()
    return {"platform_key": PLATFORM, "items": [_cap_json(cap) for cap in caps]}


@router.put("/cost-caps/{tenant_id}", openapi_extra=_CSRF_OPENAPI)
async def set_cost_cap(tenant_id: str, body: CostCapBody, request: Request,
                       agent_id: str | None = Query(default=None, max_length=64),
                       claims: dict = Depends(current_claims),
                       _tenant: str = Depends(authed_tenant),
                       _identity=Depends(require_platform_capability(Capability.set_cost_caps))) -> dict:
    """Set a monthly AI spend cap (QIK-522).

    Gated on set_cost_caps rather than view_ai_cost: reaching a cap stops a customer's workers
    answering, so this is a mutation of customer-facing behaviour, not a reporting feature.

    Use tenant_id "*" with no agent_id for the platform default. A worker cap overrides its tenant
    cap, which overrides the default.
    """
    _require_csrf(request)
    cap = CostCap(
        tenant=tenant_id, agent_id=agent_id,
        # USD in, nano-USD stored. The API speaks the unit an operator types; the store speaks the
        # unit that does not round a Titan embedding away.
        monthly_cap_nano_usd=UNLIMITED if body.monthly_cap_usd < 0
        else int(round(body.monthly_cap_usd * 1_000_000_000)),
        alert_threshold_pct=body.alert_threshold_pct,
        updated_by_email=claims.get("email"), updated_at=datetime.now(timezone.utc))
    existing = next((c for c in await request.app.state.cost_caps.list_all()
                     if c.tenant == tenant_id and c.agent_id == agent_id), None)
    saved = await request.app.state.cost_caps.upsert(cap)
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.COST_CAP_SET, target_id=f"{tenant_id}/{agent_id or ''}",
        tenant_id=tenant_id, actor_type=audit.PLATFORM_ADMIN,
        actor_id=str(claims.get("email") or ""), actor_label=str(claims.get("email") or ""),
        changes=audit.diff(
            audit_actions.COST_CAP_SET,
            {"monthly_cap_nano_usd": existing.monthly_cap_nano_usd} if existing else {},
            {"monthly_cap_nano_usd": cap.monthly_cap_nano_usd,
             "alert_threshold_pct": cap.alert_threshold_pct})), request=request)
    # Without this the new cap would not apply until the guard's cache expired, which reads as the
    # save not having worked.
    guard = getattr(request.app.state, "cost_guard", None)
    if guard is not None:
        guard.invalidate()
    return _cap_json(saved)


@router.delete("/cost-caps/{tenant_id}", openapi_extra=_CSRF_OPENAPI)
async def delete_cost_cap(tenant_id: str, request: Request,
                          agent_id: str | None = Query(default=None, max_length=64),
                          claims: dict = Depends(current_claims),
                          _tenant: str = Depends(authed_tenant),
                          _identity=Depends(require_platform_capability(Capability.set_cost_caps))) -> dict:
    _require_csrf(request)
    removed = next((c for c in await request.app.state.cost_caps.list_all()
                    if c.tenant == tenant_id and c.agent_id == agent_id), None)
    await request.app.state.cost_caps.delete(tenant_id, agent_id)
    # The cap row carried updated_by_email, so deleting the cap deleted the only record of who set it.
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.COST_CAP_REMOVED, target_id=f"{tenant_id}/{agent_id or ''}",
        tenant_id=tenant_id, actor_type=audit.PLATFORM_ADMIN,
        actor_id=str(claims.get("email") or ""), actor_label=str(claims.get("email") or ""),
        changes=audit.diff(audit_actions.COST_CAP_REMOVED,
                           {"monthly_cap_nano_usd": removed.monthly_cap_nano_usd} if removed else {},
                           {})), request=request)
    guard = getattr(request.app.state, "cost_guard", None)
    if guard is not None:
        guard.invalidate()
    return {"removed": tenant_id, "agent_id": agent_id}


class TenantRoleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=1000)


@router.put("/users/{user_id}/role", openapi_extra=_CSRF_OPENAPI)
async def set_tenant_role(user_id: str, body: TenantRoleBody, request: Request,
                          claims: dict = Depends(current_claims),
                          _tenant: str = Depends(authed_tenant),
                          _identity=Depends(require_platform_capability(Capability.manage_customers))) -> dict:
    """Change any user's TENANT role, from any tenant.

    PUT /identity/users/{id}/role already existed but is tenant-scoped: it reads the tenant from the
    caller's own token and 404s on a user outside it, so a platform admin could only change users in
    the tenant they happen to be signed into. There was no cross-tenant path at all, which is why the
    user directory was read-only.

    The tenant-facing invariants are preserved exactly, because they are correctness rules and not
    merely permission checks:
      - owner is never assignable (ASSIGNABLE_ROLES), so a tenant cannot gain a second owner;
      - the current owner's role cannot be changed, which is what stops a tenant being left ownerless
        and therefore unadministrable by its own team.

    Gated on manage_customers rather than manage_admins: this changes a customer's internal
    permissions, not platform authority. Audited, because nothing recorded a tenant role change before,
    on either the tenant-facing endpoint or anywhere else.
    """
    _require_csrf(request)
    store = get_user_store()
    # Cross-tenant: the platform-admin console resolves a user by primary key regardless of tenant,
    # which is the whole point of this endpoint. Every tenant-facing caller goes through
    # list_by_tenant or a tenant-filtered lookup.
    user = await store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    try:
        target = Role(body.role)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unknown role: {body.role}") from None
    if target not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"role '{body.role}' cannot be assigned; assignable: "
                   f"{', '.join(sorted(r.value for r in ASSIGNABLE_ROLES))}")
    if user.role is Role.owner:
        raise HTTPException(status_code=409, detail="the tenant owner's role cannot be changed")
    # No self-service, matching AdminOrg.grant. Without this, a platform admin holding manage_customers
    # who is merely a viewer in some tenant could promote THEMSELVES to tenant admin, and tenant admin
    # carries Stripe portal access, payment-link creation and subscription cancel/resume. That would
    # make manage_customers an indirect grant of manage_billing, which is exactly the separation the
    # capability split exists to enforce.
    if user.email.lower() == str(claims.get("email") or "").lower():
        raise HTTPException(status_code=409, detail="an admin cannot change their own tenant role")

    previous = user.role.value
    await store.set_role(user_id, target)
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.TENANT_ROLE_CHANGED, target_id=user_id, target_label=user.email,
        tenant_id=user.tenant, actor_type=audit.PLATFORM_ADMIN,
        actor_id=str(claims.get("email") or ""), actor_label=str(claims.get("email") or ""),
        reason=body.reason,
        changes=audit.diff(audit_actions.TENANT_ROLE_CHANGED,
                           {"role": previous}, {"role": target.value})), request=request)
    return {"id": user_id, "email": user.email, "tenant_id": user.tenant,
            "role": target.value, "role_label": ROLE_LABELS.get(target, target.value),
            "previous_role": previous}


class WorkerStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=1000)


@router.put("/workers/{tenant_id}/{agent_id}/status", openapi_extra=_CSRF_OPENAPI)
async def set_worker_status(tenant_id: str, agent_id: str, body: WorkerStatusBody, request: Request,
                            claims: dict = Depends(current_claims),
                            _tenant: str = Depends(authed_tenant),
                            _identity=Depends(require_platform_capability(Capability.manage_workers))) -> dict:
    """Set a worker's lifecycle status.

    Before this, status could only ever move forward: POST /agents/{id}/ready hardcodes "ready" and
    nothing anywhere could return a worker to training. So a worker whose ingest produced a bad corpus
    stayed advertised as ready, and the only remedy was to disable it entirely, which is a different
    and blunter statement to the customer.

    Addressed by tenant and worker rather than by customer, so it is callable from the worker directory
    where the operator actually is. Audited, because agent_state_audit models `enabled` only and has no
    shape for a status change.

    Backward only. See the guard below for why publishing is not the platform's call to make.
    """
    _require_csrf(request)
    if body.status not in AGENT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown status: {body.status}. Allowed: {', '.join(sorted(AGENT_STATUSES))}")
    # Deliberately one direction only. "ready" is the gate the PUBLIC chat checks
    # (chat/public_router.py:62), so moving a worker forward would publish it on the customer's behalf,
    # which is a claim the tenant should make and can already make via POST /agents/{id}/ready. Pulling
    # a worker back is the safety action, and it is the one this endpoint exists for.
    if body.status != "training":
        raise HTTPException(
            status_code=422,
            detail="an admin can only move a worker back to training; publishing is the tenant's call "
                   "via POST /agents/{agent_id}/ready")
    agent = await request.app.state.agents.get(tenant_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="worker not found")
    if agent.status == body.status:
        # Idempotent, and deliberately writes no audit row: a no-op is not a change.
        return _worker_json(agent) | {"tenant_id": tenant_id, "changed": False}

    previous = agent.status
    updated = await request.app.state.agents.set_status(tenant_id, agent_id, body.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="worker not found")
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.WORKER_STATUS_CHANGED, target_id=agent_id, target_label=agent.name,
        tenant_id=tenant_id, actor_type=audit.PLATFORM_ADMIN,
        actor_id=str(claims.get("email") or ""), actor_label=str(claims.get("email") or ""),
        reason=body.reason,
        changes=audit.diff(audit_actions.WORKER_STATUS_CHANGED,
                           {"status": previous}, {"status": body.status})), request=request)
    return _worker_json(updated) | {"tenant_id": tenant_id, "changed": True}


@router.get("/audit")
async def admin_audit(request: Request, _tenant: str = Depends(authed_tenant),
                      identity=Depends(require_platform_capability(Capability.view_audit)),
                      action: str | None = Query(default=None, max_length=64),
                      category: str | None = Query(default=None, max_length=24),
                      outcome: str | None = Query(default=None, max_length=16),
                      tenant_id: str | None = Query(default=None, max_length=64),
                      actor_id: str | None = Query(default=None, max_length=320),
                      target_id: str | None = Query(default=None, max_length=320),
                      request_id: str | None = Query(default=None, max_length=64),
                      search: str | None = Query(default=None, max_length=200),
                      days: int = Query(default=7, ge=1, le=400),
                      cursor: str | None = Query(default=None, max_length=64),
                      limit: int = Query(default=100, ge=1, le=500)) -> dict:
    """The platform audit trail.

    Gated on view_audit, which is NOT in the viewer default set. Read used to sit on view_customers,
    on the reasoning that knowing an operator disabled a tenant is context another operator needs. That
    reasoning still holds for the admin and access categories, but it stopped being sufficient once
    authentication events landed here: a failed-login trail tells a reader which accounts exist, when
    each colleague works and from which addresses. Wider than the write gates, narrower than the
    customer list.

    But not uniformly wider. An audit row contains the before and after of the thing it records, so
    reading the row is reading that thing. Spend caps carry amounts that GET /admin/cost-caps gates on
    view_ai_cost, and access grants carry capability sets that GET /admin/org gates on manage_admins.
    The registry declares the read capability per action, and the exclusion is applied IN SQL:
    filtering a page after fetching it returns short pages with no indication that more exist, and
    with a cursor it skips rows outright.

    Keyset paging and no total. A COUNT over a filtered multi-million-row table is what makes an audit
    page unusable, and the number is not worth a full scan. The window is bounded so no query is ever
    unbounded.
    """
    store = getattr(request.app.state, "audit", None)
    if store is None:
        return {"items": [], "next_cursor": None, "has_more": False}

    hidden = audit_actions.unreadable_actions(
        lambda capability: identity is not None and identity.can(capability))
    parsed_cursor = None
    if cursor:
        # The cursor carries the whole sort key, so paging cannot skip a row whose timestamp and id
        # disagree in order. Rejected rather than ignored when malformed: silently returning page one
        # is how a UI loops forever.
        stamp, _, raw_id = cursor.partition("|")
        try:
            parsed_cursor = (datetime.fromisoformat(stamp), int(raw_id))
        except ValueError:
            raise HTTPException(status_code=422, detail="malformed cursor") from None

    rows = await store.list(
        actions_to_hide=hidden, action=action, category=category, outcome=outcome,
        tenant_id=tenant_id, actor_id=actor_id, target_id=target_id, request_id=request_id,
        search=search, since=datetime.now(timezone.utc) - timedelta(days=days),
        cursor=parsed_cursor, limit=limit + 1)

    has_more = len(rows) > limit
    page = rows[:limit]
    return {"items": page, "next_cursor": page[-1]["_cursor"] if has_more and page else None,
            "has_more": has_more, "window_days": days,
            # Stated rather than left as a silent gap, so an operator who cannot see spend events knows
            # they exist rather than concluding nothing happened.
            "hidden_actions": len(hidden)}


@router.get("/audit/actions")
async def audit_action_catalogue(
        _tenant: str = Depends(authed_tenant),
        identity=Depends(require_platform_capability(Capability.view_audit))) -> dict:
    """The action taxonomy, so the UI builds its filters from the same source of truth as the writer
    instead of a hardcoded list that drifts."""
    def can(capability) -> bool:
        return identity is not None and identity.can(capability)

    visible = [spec for spec in audit_actions.REGISTRY.values()
               if spec.read_capability is None or can(spec.read_capability)]
    return {"categories": sorted({spec.category for spec in visible}),
            "actions": [{"action": spec.action, "category": spec.category,
                         "target_type": spec.target_type}
                        for spec in sorted(visible, key=lambda s: (s.category, s.action))]}


class EraseSubjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The address to erase. In the body, never the query string: the whole point is to remove this value
    # from durable storage, and an edge access log is durable storage we do not control.
    identifier: str = Field(min_length=3, max_length=320)
    # The DSAR or incident ticket this was performed under. Required, because an erasure with no
    # reference is an erasure nobody can justify later, and the mapping from the reference back to the
    # person is what lives in the ticket rather than here.
    request_ref: str = Field(min_length=1, max_length=64)


@router.post("/audit/erase", openapi_extra=_CSRF_OPENAPI)
async def erase_subject(body: EraseSubjectBody, request: Request,
                        claims: dict = Depends(current_claims),
                        _tenant: str = Depends(authed_tenant),
                        _identity=Depends(require_platform_capability(Capability.manage_admins))) -> dict:
    """Pseudonymise a subject throughout the audit trail, for an erasure request.

    Rows are never deleted. A gap in an audit trail is indistinguishable from tampering, and removing
    rows to satisfy an erasure request destroys the completeness the table exists for. The identifying
    fields are replaced with a keyed pseudonym and everything else, the timestamps, the action, the
    outcome, the diffs, is left exactly as it was: the row still proves that something happened, to whom
    under a stable pseudonym, and when.

    The erasure event itself must not re-create the address it just removed, which is the circularity
    that catches most implementations. So this records the pseudonym, the request reference and a row
    count, and never the identifier. The mapping from reference to person lives in the DSAR ticket under
    its own retention, which is where a regulator expects to find it.

    Gated on manage_admins rather than manage_customers. This rewrites the evidence trail, which is a
    higher privilege than acting on a customer, and it is the same gate that protects platform authority.

    QUEUED RATHER THAN PERFORMED HERE. Erasure is the only operation that UPDATEs audit_events, so doing
    it in the request meant this process had to hold a connection able to rewrite history, while every
    other write path used one that could not. That made the append-only boundary one handler away from
    meaning nothing. The work now runs on the worker, which is the only place the privileged connection
    exists.

    The cost is that this returns "accepted" instead of a row count. For a request that takes days to
    fulfil, seconds of asynchrony is not a real loss, and the count still lands in the trail under the
    same request reference.
    """
    _require_csrf(request)
    queue = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="task queue unavailable")

    # The pseudonym is returned immediately because it needs no database at all: it is an HMAC of the
    # address. So the operator gets the value they will need to find the rows afterwards, even though the
    # work itself has not run yet.
    pseudonym = audit_retention.audit_subject_pseudonym(body.identifier)
    await queue.enqueue(
        "erase_audit_subject", identifier=body.identifier, pseudonym=pseudonym,
        request_ref=body.request_ref, actor_email=str(claims.get("email") or ""))

    # 202, not 200: accepted rather than done. The row count is not knowable here and inventing one would
    # be worse than omitting it. It appears in the trail, findable by this request reference.
    return JSONResponse(status_code=202, content={
        "pseudonym": pseudonym, "request_ref": body.request_ref, "status": "queued",
        "where_to_check": f"/audit?q={body.request_ref}"})


@router.get("/audit/retention")
async def audit_retention_policy(_tenant: str = Depends(authed_tenant),
                                 _identity=Depends(require_platform_capability(Capability.view_audit))) -> dict:
    """The retention policy as the code enforces it, not as a document claims.

    Surfaced so the operator UI can state it on the page and so the number an auditor is told is read
    from the same constant the cron job uses. A stated policy that differs from the implemented one is
    the specific thing both SOC 2 and a data protection review check for.
    """
    return {"event_retention_days": audit_retention.EVENT_RETENTION_DAYS,
            "network_retention_days": audit_retention.NETWORK_RETENTION_DAYS,
            "erasure": "pseudonymised in place; rows are never deleted for erasure",
            "archive": "not yet implemented"}
