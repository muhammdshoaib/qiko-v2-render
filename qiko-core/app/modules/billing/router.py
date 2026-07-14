"""Billing HTTP API: Stripe webhook receiver + subscription lifecycle (tenant-scoped)."""
from __future__ import annotations

from dataclasses import asdict

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import (
    authed_tenant,
    get_payment_links,
    get_stripe_webhook,
    get_subscriptions,
    get_teams,
    require_role,
)
from app.modules.billing.team_billing import team_plan
from app.modules.billing.webhook import verify_stripe_signature
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default=""),
                         handler=Depends(get_stripe_webhook)) -> dict:
    body = await request.body()
    s = get_settings()
    if s.stripe_webhook_secret:
        if not verify_stripe_signature(s.stripe_webhook_secret, body, stripe_signature):
            raise HTTPException(status_code=400, detail="invalid signature")
    elif not s.debug:  # fail closed outside dev: refuse unverifiable webhooks
        raise HTTPException(status_code=400, detail="webhook signature secret not configured")
    import json
    return {"action": handler.handle(json.loads(body or b"{}"))}


class ActivateBody(BaseModel):
    plan: str = "pro"


# Every lifecycle endpoint below derives its subject from `authed_tenant` (the verified token
# claim) and NEVER from a client-supplied id. That structurally closes the cross-tenant BOLA
# (OWASP A01/API1): there is simply no request field a caller could set to act on another
# tenant's subscription. The `customer_id` echoed back in responses is the tenant, kept only for
# client-shape continuity.
@router.get("/subscription")
def subscription_status(tenant: str = Depends(authed_tenant), subs=Depends(get_subscriptions)) -> dict:
    sub = subs.status(tenant)
    if not sub:
        return {"customer_id": tenant, "status": "none"}
    return {"customer_id": tenant, "plan": sub.plan, "status": sub.status,
            "cancel_at_period_end": sub.cancel_at_period_end}


@router.post("/subscription/activate")
def activate(body: ActivateBody, tenant: str = Depends(authed_tenant),
             _role: dict = Depends(require_role(Role.admin)), subs=Depends(get_subscriptions)) -> dict:
    sub = subs.activate(tenant, body.plan)
    return {"customer_id": tenant, "plan": sub.plan, "status": sub.status}


class CheckoutBody(BaseModel):
    plan: str = "pro"
    price_id: str = "price_default"
    promo: str | None = None


@router.get("/plans")
def plans() -> list[dict]:
    """Public pricing catalog (for the onboarding plan step and the Pricing page). Real product
    shows Premium + Enterprise as self-serve/contact-sales tiers (verified live on
    stage-app.qiko.ai/app/pricing) -- Basic is a contact-sales-only tier, not listed here."""
    from app.modules.billing.plans import list_plans

    out = []
    for i, p in enumerate(list_plans(), start=1):
        is_custom = p.price_cents < 0
        out.append({
            "id": i, "name": p.display_name, "price_id": f"price_{p.name}",
            "amount": 0 if is_custom else p.price_cents, "interval": "month",
            "display_price": "Custom Pricing" if is_custom else f"${p.price_cents // 100}",
            "worker_limit": p.worker_limit,
            "features": p.features,
        })
    return out


@router.post("/checkout")
def checkout(body: CheckoutBody, tenant: str = Depends(authed_tenant), subs=Depends(get_subscriptions)) -> dict:
    try:
        return {"url": subs.start_checkout(tenant, body.plan, price_id=body.price_id, promo=body.promo)}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="payment provider error") from e


@router.get("/portal")
def portal(tenant: str = Depends(authed_tenant), subs=Depends(get_subscriptions)) -> dict:
    try:
        return {"url": subs.portal_url(tenant)}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="payment provider error") from e


@router.post("/subscription/cancel")
def cancel(tenant: str = Depends(authed_tenant), subs=Depends(get_subscriptions)) -> dict:
    try:
        sub = subs.cancel(tenant)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="no subscription") from e
    return {"customer_id": tenant, "status": sub.status, "cancel_at_period_end": sub.cancel_at_period_end}


@router.post("/subscription/resume")
def resume(tenant: str = Depends(authed_tenant), subs=Depends(get_subscriptions)) -> dict:
    try:
        sub = subs.resume(tenant)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"customer_id": tenant, "status": sub.status, "cancel_at_period_end": sub.cancel_at_period_end}


class PaymentLinkBody(BaseModel):
    customer_email: str
    amount_cents: int
    recurring: bool = False


@router.post("/payment-links")
def create_payment_link(body: PaymentLinkBody, _tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.admin)), links=Depends(get_payment_links)) -> dict:
    try:
        log = links.create(body.customer_email, body.amount_cents, recurring=body.recurring)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="payment provider error") from e
    return {"session_id": log.session_id, "url": log.url, "status": log.status}


class MarkPaidBody(BaseModel):
    customer_email: str = Field(min_length=3)


@router.post("/payment-links/mark-paid")
def mark_paid(body: MarkPaidBody, _tenant: str = Depends(authed_tenant),
              _role: dict = Depends(require_role(Role.admin)), links=Depends(get_payment_links)) -> dict:
    # Validated body (was a raw dict -> a missing customer_email 500'd instead of a clean 422).
    return {"marked": links.mark_as_paid_for_user(body.customer_email)}


@router.get("/payment-links")
def list_payment_links(email: str, _tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.admin)), links=Depends(get_payment_links)) -> list[dict]:
    return [asdict(x) for x in links.logs_for(email)]


@router.get("/team/{team_id}/plan")
async def team_billing_plan(team_id: str, tenant: str = Depends(authed_tenant),
                            subs=Depends(get_subscriptions), teams=Depends(get_teams)) -> dict:
    # Same cross-tenant BOLA class as teams/router.py: TeamService.members() takes a bare team_id
    # with no tenant check of its own, so without this an outsider could read another tenant's
    # team membership + billing plan just by knowing/guessing its team_id.
    team = await teams.get(team_id)
    if team is None or team.tenant != tenant:
        raise HTTPException(status_code=404, detail="team not found")
    return {"team_id": team_id, "plan": team_plan(list(team.members), subs).name}


@router.get("/invoices")
def invoices(_tenant: str = Depends(authed_tenant), _role: dict = Depends(require_role(Role.admin)),
             handler=Depends(get_stripe_webhook), customer_id: str | None = None) -> list[dict]:
    return [asdict(i) for i in handler.invoices.list(customer_id)]
