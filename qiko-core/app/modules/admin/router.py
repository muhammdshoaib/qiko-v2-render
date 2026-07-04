"""Admin HTTP API (tenant-scoped). Revenue computed from a single source (the posted subs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.deps import authed_tenant, require_role
from app.modules.admin.metrics import Subscription, revenue_metrics
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/admin", tags=["admin"])


class SubscriptionIn(BaseModel):
    customer_id: str
    plan: str
    price_cents: int
    interval: str = "month"
    status: str = "active"


@router.post("/revenue")
def revenue(subs: list[SubscriptionIn], _tenant: str = Depends(authed_tenant),
            _role: dict = Depends(require_role(Role.admin))) -> dict:
    return revenue_metrics([Subscription(**s.model_dump()) for s in subs])


@router.get("/customers")
def customers(request: Request, _tenant: str = Depends(authed_tenant),
              _role: dict = Depends(require_role(Role.admin)),
              search: str | None = None, plan: str | None = None, page: int = 1) -> dict:
    directory = request.app.state.customers
    result = directory.list(search=search, plan=plan, page=page)
    return {"total": result["total"], "page": result["page"],
            "items": [{"user_id": r.user_id, "email": r.email, "plan": r.plan,
                       "earnings_cents": r.earnings_cents} for r in result["items"]]}


def _customer_json(r) -> dict:
    return {"user_id": r.user_id, "email": r.email, "plan": r.plan,
            "earnings_cents": r.earnings_cents, "is_studio": r.is_studio, "deleted": r.deleted}


@router.get("/customers/{user_id}")
def customer_detail(user_id: str, request: Request, _tenant: str = Depends(authed_tenant),
                    _role: dict = Depends(require_role(Role.admin))) -> dict:
    rec = request.app.state.customers.details(user_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return _customer_json(rec)


class StudioBody(BaseModel):
    enabled: bool


@router.post("/customers/{user_id}/studio")
def customer_studio(user_id: str, body: StudioBody, request: Request, _tenant: str = Depends(authed_tenant),
                    _role: dict = Depends(require_role(Role.admin))) -> dict:
    try:
        return _customer_json(request.app.state.customers.set_studio(user_id, body.enabled))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="customer not found") from e


@router.delete("/customers/{user_id}")
def customer_delete(user_id: str, request: Request, _tenant: str = Depends(authed_tenant),
                    _role: dict = Depends(require_role(Role.admin))) -> dict:
    try:
        return _customer_json(request.app.state.customers.soft_delete(user_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="customer not found") from e


@router.get("/overview")
def overview(request: Request, _tenant: str = Depends(authed_tenant),
             _role: dict = Depends(require_role(Role.admin))) -> dict:
    subs = request.app.state.subscriptions.summary()
    customers_total = request.app.state.customers.list()["total"]
    return {"customers_total": customers_total, **subs}


@router.get("/analytics")
def analytics(request: Request, _tenant: str = Depends(authed_tenant),
              _role: dict = Depends(require_role(Role.admin)),
              start: str = "2026-01-01", end: str = "2026-12-31") -> dict:
    from app.modules.admin.ga4 import GA4Analytics

    return GA4Analytics(request.app.state.ga4).dashboard(start, end)
