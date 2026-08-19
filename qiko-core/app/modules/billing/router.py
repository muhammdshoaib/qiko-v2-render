"""Billing HTTP API: Stripe webhook receiver + subscription lifecycle (tenant-scoped)."""
from __future__ import annotations

from dataclasses import asdict

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Query
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.deps import (
    authed_tenant,
    current_claims,
    get_payment_links,
    get_stripe_webhook,
    get_subscriptions,
    get_teams,
    require_platform_capability,
    require_role,
)
from app.modules.billing.subscriptions import AlreadySubscribedError, CheckoutUnavailableError
from app.modules.billing.team_billing import team_plan
from app.modules.billing.webhook import Invoice, verify_stripe_signature
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.identity import csrf
from app.modules.admin.pagination import MAX_PAGE_SIZE, PAGE_SIZE, paginate
from app.modules.admin.sorting import INVOICE_SORTS, apply_sort
from app.modules.identity.admin_rbac import Capability
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
def subscription_status(tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.admin)),
                        subs=Depends(get_subscriptions)) -> dict:
    sub = subs.status(tenant)
    if not sub:
        return {"customer_id": tenant, "status": "none"}
    return {"customer_id": tenant, "plan": sub.plan, "status": sub.status,
            "cancel_at_period_end": sub.cancel_at_period_end}


@router.post("/subscription/activate")
def activate(body: ActivateBody, tenant: str = Depends(authed_tenant),
             _role: dict = Depends(require_role(Role.admin)), subs=Depends(get_subscriptions)) -> dict:
    # Development helper only. Production subscription activation comes from a verified Stripe
    # webhook, never a customer-selected plan in an authenticated request.
    if not get_settings().debug:
        raise HTTPException(status_code=404, detail="not found")
    sub = subs.activate(tenant, body.plan)
    return {"customer_id": tenant, "plan": sub.plan, "status": sub.status}


class CheckoutBody(BaseModel):
    plan: str = "pro"
    # Ignored server-side (retained for backward-compat with existing clients that still send it):
    # the real Stripe price is resolved from config by plan, so a client cannot pick the price.
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
            "key": p.name,
            "id": i, "name": p.display_name, "display_name": p.display_name,
            "price_id": f"price_{p.name}",
            "amount": 0 if is_custom else p.price_cents, "interval": "month",
            "display_price": "Custom Pricing" if is_custom else f"${p.price_cents // 100}",
            "worker_limit": p.worker_limit,
            "features": p.features,
        })
    return out


@router.post("/checkout")
def checkout(request: Request, body: CheckoutBody, tenant: str = Depends(authed_tenant),
             subs=Depends(get_subscriptions)) -> dict:
    # State-changing request from the creator UI: require the double-submit CSRF token.
    csrf.require_csrf(request)
    # The real Stripe price is resolved server-side from config (client-supplied price_id is ignored
    # for security). When Stripe isn't provisioned for the plan, return a clear 503 instead of a 404
    # or a broken redirect, so the UI can show "checkout unavailable" and a retry.
    try:
        return {"url": subs.start_checkout(tenant, body.plan, promo=body.promo)}
    except CheckoutUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except AlreadySubscribedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="payment provider error") from e


@router.get("/portal")
def portal(tenant: str = Depends(authed_tenant),
           _role: dict = Depends(require_role(Role.admin)),
           subs=Depends(get_subscriptions)) -> dict:
    try:
        return {"url": subs.portal_url(tenant)}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="payment provider error") from e


@router.post("/subscription/cancel")
def cancel(tenant: str = Depends(authed_tenant),
           _role: dict = Depends(require_role(Role.admin)),
           subs=Depends(get_subscriptions)) -> dict:
    try:
        sub = subs.cancel(tenant)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="no subscription") from e
    return {"customer_id": tenant, "status": sub.status, "cancel_at_period_end": sub.cancel_at_period_end}


@router.post("/subscription/resume")
def resume(tenant: str = Depends(authed_tenant),
           _role: dict = Depends(require_role(Role.admin)),
           subs=Depends(get_subscriptions)) -> dict:
    try:
        sub = subs.resume(tenant)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"customer_id": tenant, "status": sub.status, "cancel_at_period_end": sub.cancel_at_period_end}


class PaymentLinkBody(BaseModel):
    customer_email: str = Field(min_length=3, max_length=320)
    amount_cents: int = Field(gt=0, le=100_000_000)
    recurring: bool = False

    @field_validator("recurring")
    @classmethod
    def reject_unwired_recurring_links(cls, value: bool) -> bool:
        if value:
            raise ValueError("recurring payment links are not enabled")
        return value

    @field_validator("customer_email")
    @classmethod
    def validate_customer_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, separator, domain = value.partition("@")
        if (not separator or not local or "." not in domain
                or domain.startswith(".") or domain.endswith(".")):
            raise ValueError("customer_email must be a valid address")
        return value


@router.post("/payment-links")
def create_payment_link(body: PaymentLinkBody, request: Request,
                        claims: dict = Depends(current_claims),
                        _tenant: str = Depends(authed_tenant),
                        _identity=Depends(require_platform_capability(Capability.manage_billing)), links=Depends(get_payment_links)) -> dict:
    """Create a Stripe payment link and email it to a customer.

    Audited as an attempt and then an outcome, rather than one row after the fact. The effect is at
    Stripe, so no database transaction can contain it: if the call times out, the link may well exist
    and the customer may already have been emailed. An attempt with no matching outcome is exactly the
    row an operator needs in order to go and look.
    """
    csrf.require_csrf(request)
    actor = str(claims.get("email") or "")
    changes = audit.diff(audit_actions.PAYMENT_LINK_ATTEMPTED, {}, {
        "amount_cents": body.amount_cents, "customer_email": body.customer_email,
        "recurring": body.recurring})
    audit.record_sync(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.PAYMENT_LINK_ATTEMPTED, target_id=body.customer_email,
        actor_type=audit.PLATFORM_ADMIN, actor_id=actor, actor_label=actor,
        changes=changes), request=request)
    try:
        log = links.create(body.customer_email, body.amount_cents, recurring=body.recurring)
    except httpx.HTTPError as e:
        audit.record_sync(request.app.state.audit, audit.AuditEvent(
            action=audit_actions.PAYMENT_LINK_CREATED, target_id=body.customer_email,
            actor_type=audit.PLATFORM_ADMIN, actor_id=actor, actor_label=actor,
            outcome=audit.FAILURE, changes=changes,
            metadata={"error": type(e).__name__}), request=request)
        raise HTTPException(status_code=502, detail="payment provider error") from e
    audit.record_sync(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.PAYMENT_LINK_CREATED, target_id=log.session_id,
        target_label=body.customer_email, actor_type=audit.PLATFORM_ADMIN,
        actor_id=actor, actor_label=actor, changes=changes,
        metadata={"session_id": log.session_id}), request=request)
    return {"session_id": log.session_id, "url": log.url, "status": log.status}


class MarkPaidBody(BaseModel):
    customer_email: str = Field(min_length=3)


@router.post("/payment-links/mark-paid")
def mark_paid(body: MarkPaidBody, request: Request, claims: dict = Depends(current_claims),
              _tenant: str = Depends(authed_tenant),
              _identity=Depends(require_platform_capability(Capability.manage_billing)), links=Depends(get_payment_links)) -> dict:
    """Mark a customer's payment links paid without a payment having been received.

    An operator declaring money received. If one row in this table ever matters in a dispute, it is
    this one, and until now it left no trace at all. Purely local, unlike link creation, so it is
    recorded once with its outcome rather than as an attempt and a result.
    """
    csrf.require_csrf(request)
    # Validated body (was a raw dict -> a missing customer_email 500'd instead of a clean 422).
    marked = links.mark_as_paid_for_user(body.customer_email)
    actor = str(claims.get("email") or "")
    audit.record_sync(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.PAYMENT_LINK_MARKED_PAID, target_id=body.customer_email,
        actor_type=audit.PLATFORM_ADMIN, actor_id=actor, actor_label=actor,
        changes=audit.diff(audit_actions.PAYMENT_LINK_MARKED_PAID,
                           {"status": "pending"}, {"status": "paid", "links_marked": marked})),
        request=request)
    return {"marked": marked}


@router.get("/payment-links")
def list_payment_links(email: str, _tenant: str = Depends(authed_tenant),
                       _identity=Depends(require_platform_capability(Capability.manage_billing)), links=Depends(get_payment_links)) -> list[dict]:
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
def invoices(_tenant: str = Depends(authed_tenant),
             _identity=Depends(require_platform_capability(Capability.manage_billing)),
             handler=Depends(get_stripe_webhook), customer_id: str | None = None,
             search: str | None = Query(default=None, max_length=200),
             status: str | None = Query(default=None, max_length=40),
             sort: str | None = Query(default=None, max_length=40),
             order: str = Query(default="asc", pattern="^(asc|desc)$"),
             page: int = Query(default=1, ge=1),
             page_size: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)) -> dict:
    """Synced Stripe invoices, paginated and sortable like every other admin directory.

    It returned a bare list. With one customer that is fine; with a year of monthly invoices across a
    hundred accounts it is a page that loads everything and offers no way to find anything, and the
    console had no other list left that behaved that way.

    The shape now matches the directories exactly: total, page, page_size, items. The admin table reads
    page_size back rather than assuming it, so a clamp here cannot desynchronise the ranges there.
    """
    rows = [asdict(i) for i in handler.invoices.list(customer_id)]
    if search:
        needle = search.strip().lower()
        rows = [r for r in rows
                if needle in r["stripe_invoice_id"].lower() or needle in r["customer_id"].lower()]
    if status:
        rows = [r for r in rows if r["status"] == status]
    rows = apply_sort(rows, INVOICE_SORTS, sort, order)
    result = paginate(rows, page=page, page_size=page_size)
    return {"total": result["total"], "page": result["page"], "page_size": page_size,
            "items": result["items"]}


class CreateInvoiceBody(BaseModel):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_cents: int = Field(gt=0, le=100_000_000)
    currency: str = Field(default="usd", max_length=3)
    description: str = Field(default="", max_length=500)
    send: bool = False


@router.post("/invoices")
def create_invoice(request: Request, body: CreateInvoiceBody,
                   claims: dict = Depends(current_claims),
                   _identity=Depends(require_platform_capability(Capability.manage_billing)),
                   subs=Depends(get_subscriptions), handler=Depends(get_stripe_webhook)) -> dict:
    csrf.require_csrf(request)
    actor = str(claims.get("email") or "")
    # customer_id may be a Stripe customer id or a tenant id with a linked Stripe customer.
    customer = body.customer_id
    if not customer.startswith("cus_"):
        customer = subs.stripe_customer_ref(customer)
    if not customer.startswith("cus_"):
        raise HTTPException(status_code=400, detail="no Stripe customer id for this tenant")
    try:
        inv = subs.gateway.create_invoice(
            customer_id=customer, amount_cents=body.amount_cents, currency=body.currency,
            description=body.description, send=body.send)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="payment provider error") from e
    stored = Invoice(
        stripe_invoice_id=inv["id"], customer_id=customer,
        amount_cents=inv.get("amount_due", body.amount_cents), status=inv.get("status", "open"),
        currency=inv.get("currency"), number=inv.get("number"),
        hosted_invoice_url=inv.get("hosted_invoice_url"), invoice_pdf=inv.get("invoice_pdf"))
    handler.invoices.upsert(stored)
    audit.record_sync(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.INVOICE_CREATED, target_id=stored.stripe_invoice_id,
        target_label=customer, actor_type=audit.PLATFORM_ADMIN,
        actor_id=actor, actor_label=actor,
        changes=audit.diff(audit_actions.INVOICE_CREATED, {}, {
            "amount_cents": body.amount_cents, "currency": body.currency,
            "customer_id": body.customer_id, "description": body.description})),
        request=request)
    return asdict(stored)


@router.post("/invoices/reconcile")
def reconcile_invoices_route(request: Request, claims: dict = Depends(current_claims),
                             _identity=Depends(require_platform_capability(Capability.manage_billing))) -> dict:
    csrf.require_csrf(request)
    actor = str(claims.get("email") or "")
    result = request.app.state.invoice_reconciliation.reconcile()
    audit.record_sync(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.INVOICE_RECONCILED, target_id="billing",
        actor_type=audit.PLATFORM_ADMIN, actor_id=actor, actor_label=actor,
        changes=audit.diff(audit_actions.INVOICE_RECONCILED, {}, result)),
        request=request)
    return result
