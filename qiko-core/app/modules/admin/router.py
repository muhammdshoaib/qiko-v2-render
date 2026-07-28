"""Admin HTTP API (tenant-scoped). Revenue computed from a single source (the posted subs)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import (
    authed_tenant,
    current_claims,
    require_platform_admin,
    require_platform_super_admin,
)
from app.modules.admin.metrics import Subscription, revenue_metrics
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import AdminRole

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminSelfOut(BaseModel):
    role: AdminRole


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
            _role=Depends(require_platform_admin())) -> dict:
    return revenue_metrics([Subscription(**s.model_dump()) for s in subs])


@router.get("/customers")
def customers(request: Request, _tenant: str = Depends(authed_tenant),
              _role=Depends(require_platform_admin()),
              search: str | None = None, plan: str | None = None, page: int = 1) -> dict:
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
                   role=Depends(require_platform_admin())) -> dict:
    return {"role": role.value}


@router.get("/customers/{user_id}", response_model=CustomerDetailOut)
async def customer_detail(user_id: str, request: Request,
                          _tenant: str = Depends(authed_tenant),
                          _role=Depends(require_platform_admin())) -> dict:
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
                             _role=Depends(require_platform_super_admin())) -> dict:
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
                          _role=Depends(require_platform_super_admin())) -> dict:
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
                          _role=Depends(require_platform_super_admin())) -> dict:
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
             _role=Depends(require_platform_admin())) -> dict:
    subs = request.app.state.subscriptions.summary()
    customers_total = request.app.state.customers.list()["total"]
    return {"customers_total": customers_total, **subs}


@router.get("/analytics")
def analytics(request: Request, _tenant: str = Depends(authed_tenant),
              _role=Depends(require_platform_admin()),
              start: str = "2026-01-01", end: str = "2026-12-31") -> dict:
    from app.modules.admin.ga4 import GA4Analytics

    return GA4Analytics(request.app.state.ga4).dashboard(start, end)
