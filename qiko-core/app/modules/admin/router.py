"""Admin HTTP API (tenant-scoped). Revenue computed from a single source (the posted subs)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import (
    get_user_store,
    require_platform_capability,
    require_platform_identity,
    authed_tenant,
    current_claims,
)
from app.modules.admin.metrics import Subscription, revenue_metrics
from app.modules.admin.pagination import paginate
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import AdminRole, Capability
from app.modules.identity.team_access import ROLE_LABELS

router = APIRouter(prefix="/admin", tags=["admin"])


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
              page: int = Query(default=1, ge=1)) -> dict:
    directory = request.app.state.customers
    result = directory.list(search=search, plan=plan, page=page)
    return {"total": result["total"], "page": result["page"],
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
                          _tenant: str = Depends(authed_tenant),
                          _identity=Depends(require_platform_capability(Capability.manage_customers))) -> dict:
    if await run_in_threadpool(request.app.state.customers.details, user_id) is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _require_csrf(request)
    try:
        record = await run_in_threadpool(
            request.app.state.customers.set_studio, user_id, body.enabled
        )
        return _customer_json(record)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="customer not found") from exc


@router.delete("/customers/{user_id}", openapi_extra=_CSRF_OPENAPI)
async def customer_delete(user_id: str, request: Request,
                          _tenant: str = Depends(authed_tenant),
                          _identity=Depends(require_platform_capability(Capability.manage_customers))) -> dict:
    if await run_in_threadpool(request.app.state.customers.details, user_id) is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _require_csrf(request)
    try:
        record = await run_in_threadpool(request.app.state.customers.soft_delete, user_id)
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
              start: str = "2026-01-01", end: str = "2026-12-31") -> dict:
    from app.modules.admin.ga4 import GA4Analytics

    return GA4Analytics(request.app.state.ga4).dashboard(start, end)


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
            page: int = Query(default=1, ge=1)) -> dict:
    """The tenant directory (QIK-515).

    A "customer" already IS a tenant in this codebase, so this is the same rows as /admin/customers
    with the counts the console needs and never had: how many people are on the account and how many
    workers it runs. Both were already derivable and simply not surfaced.
    """
    result = request.app.state.customers.list(search=search, plan=plan, page=page)
    return {"total": result["total"], "page": result["page"], "items": [{
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
                page: int = Query(default=1, ge=1)) -> dict:
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

    result = paginate(rows, page=page)
    return {"total": result["total"], "page": result["page"],
            "items": [_user_directory_json(user, platform, show_authority=show_authority)
                      for user in result["items"]]}


class WorkerDirectoryRow(AdminWorkerOut):
    tenant_id: str


@router.get("/workers")
async def workers(request: Request, _tenant: str = Depends(authed_tenant),
                  _identity=Depends(require_platform_capability(Capability.view_customers)),
                  search: str | None = Query(default=None, max_length=200),
                  tenant_id: str | None = Query(default=None, max_length=64),
                  enabled: bool | None = None, page: int = Query(default=1, ge=1)) -> dict:
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

    result = paginate(rows, page=page)
    return {"total": result["total"], "page": result["page"],
            "items": [{**_worker_json(agent), "tenant_id": agent.tenant}
                      for agent in result["items"]]}


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
                            page: int = Query(default=1, ge=1)) -> dict:
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

    # Busiest first: an operator opening this page is looking for the outliers, not an alphabet.
    rows.sort(key=lambda row: (-row["calls"], row["tenant_id"] or "", row["id"]))
    result = paginate(rows, page=page)
    return {"total": result["total"], "page": result["page"], "window_days": days,
            "cost_visible": show_cost, "items": result["items"]}
