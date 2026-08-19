"""Stripe subscription lifecycle over the plan catalog.

Stripe I/O sits behind a StripeGateway protocol so the lifecycle logic (checkout -> active ->
cancel-at-period-end -> resume) is testable without the network. A real StripeGateway (lazy
`stripe`) is used in prod; a fake drives the tests.

Subscription STATE (the subscriptions themselves + the tenant<->Stripe-customer mapping) sits
behind a SubscriptionStore protocol. The default is in-memory (dev/tests); the live app swaps in
the Postgres-backed store (app.db.sync_stores.SqlSubscriptionStore) under USE_DB_STORES so a
tenant's plan/status survives a restart instead of being wiped on every redeploy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.modules.billing.plans import SELF_SERVE_PLANS, Plan, get_plan, stripe_price_for


class CheckoutUnavailableError(Exception):
    """Raised when a plan has no self-serve Stripe price configured (Stripe not provisioned yet, or
    the plan is contact-sales/trial). The router maps this to a clear 503, never a 404 or a redirect."""


class AlreadySubscribedError(Exception):
    """Raised when a tenant that already has an active paid subscription tries to start a new
    self-serve checkout, which would create duplicate charges. The router maps this to 409."""


class StripeGateway(Protocol):
    def create_checkout_session(self, *, customer_id: str, price_id: str, promo: str | None,
                                client_reference_id: str | None = None, plan: str | None = None) -> str: ...
    def billing_portal_url(self, *, customer_id: str) -> str: ...
    def create_invoice(self, *, customer_id: str, amount_cents: int, currency: str = "usd",
                       description: str = "", send: bool = False) -> dict: ...
    def cancel_subscription(self, *, stripe_subscription_id: str) -> None: ...
    def resume_subscription(self, *, stripe_subscription_id: str) -> None: ...


@dataclass
class Subscription:
    customer_id: str
    plan: str
    status: str = "active"          # active | canceled
    cancel_at_period_end: bool = False
    stripe_subscription_id: str | None = None
    current_period_end: datetime | None = None


class SubscriptionStore(Protocol):
    """State backend for SubscriptionService. Both the in-memory store and the Postgres-backed
    SqlSubscriptionStore implement this synchronous interface, so the service (and every caller
    of it) is unchanged whichever is wired in."""
    def get(self, subject: str) -> Subscription | None: ...
    def put(self, sub: Subscription) -> None: ...
    def all(self) -> list[Subscription]: ...
    def get_customer(self, tenant: str) -> str | None: ...
    def set_customer(self, tenant: str, stripe_customer_id: str) -> None: ...
    def get_tenant_by_customer(self, stripe_customer_id: str) -> str | None: ...


@dataclass
class InMemorySubscriptionStore:
    """Process-local subscription state (dev/tests). Lost on restart -- the live app uses the
    Postgres-backed store instead. The subscription subject is the authenticated TENANT (matches
    agents-gating in agents/router.py: `subs.status(tenant)`), except for team billing which keys
    by member user id; `_subs` is keyed by whichever the caller passes."""
    _subs: dict[str, Subscription] = field(default_factory=dict)
    # tenant -> real Stripe customer id ("cus_..."), set from the checkout webhook.
    _customers: dict[str, str] = field(default_factory=dict)
    # Reverse lookup: Stripe customer id -> tenant.
    _tenant_by_customer: dict[str, str] = field(default_factory=dict)

    def get(self, subject: str) -> Subscription | None:
        return self._subs.get(subject)

    def put(self, sub: Subscription) -> None:
        self._subs[sub.customer_id] = sub

    def all(self) -> list[Subscription]:
        return list(self._subs.values())

    def get_customer(self, tenant: str) -> str | None:
        return self._customers.get(tenant)

    def set_customer(self, tenant: str, stripe_customer_id: str) -> None:
        self._customers[tenant] = stripe_customer_id
        self._tenant_by_customer[stripe_customer_id] = tenant

    def get_tenant_by_customer(self, stripe_customer_id: str) -> str | None:
        return self._tenant_by_customer.get(stripe_customer_id)


@dataclass
class SubscriptionService:
    gateway: StripeGateway
    store: SubscriptionStore = field(default_factory=InMemorySubscriptionStore)

    def link_customer(self, tenant: str, stripe_customer_id: str) -> None:
        """Record the real Stripe customer id for a tenant (set from the webhook on checkout)."""
        self.store.set_customer(tenant, stripe_customer_id)

    def stripe_customer_ref(self, tenant: str) -> str:
        """The Stripe customer id linked to this tenant if known, else the tenant string itself
        as a stable client-reference until a real Stripe customer exists for it."""
        return self.store.get_customer(tenant) or tenant

    def start_checkout(self, tenant: str, plan_name: str, *, promo: str | None = None) -> str:
        get_plan(plan_name)  # validate plan exists
        # Only self-serve plans can be checked out (free is a trial, enterprise is contact-sales).
        if plan_name not in SELF_SERVE_PLANS:
            raise CheckoutUnavailableError(f"plan '{plan_name}' is not available for self-serve checkout")
        existing = self.status(tenant)
        if existing is not None and existing.status == "active" and existing.plan != "free":
            raise AlreadySubscribedError(f"tenant already has an active {existing.plan} subscription")
        # The price is resolved SERVER-SIDE from config, never from client input, so a caller cannot
        # check out against an arbitrary Stripe price. In dev/stub (debug) fall back to a placeholder
        # so the flow is exercisable without real Stripe; in prod an empty price fails closed (503).
        price_id = stripe_price_for(plan_name)
        if not price_id:
            from app.core.config import get_settings

            if get_settings().debug:
                price_id = f"price_{plan_name}"
            else:
                raise CheckoutUnavailableError(
                    f"self-serve checkout is not available yet for plan '{plan_name}' (Stripe price not configured)")
        # `client_reference_id=tenant` + metadata[plan] let the checkout.session.completed webhook tie
        # the Stripe customer to our tenant and activate the CORRECT plan (see webhook.py).
        return self.gateway.create_checkout_session(
            customer_id=self.stripe_customer_ref(tenant), price_id=price_id, promo=promo,
            client_reference_id=tenant, plan=plan_name)

    def activate(self, customer_id: str, plan_name: str) -> Subscription:
        """Called on checkout.session.completed (webhook) to mark the subscription active."""
        sub = Subscription(customer_id=customer_id, plan=plan_name, status="active")
        self.store.put(sub)
        return sub

    def portal_url(self, tenant: str) -> str:
        return self.gateway.billing_portal_url(customer_id=self.stripe_customer_ref(tenant))

    # NOTE: status/activate/cancel/resume/plan_for key subscriptions by whatever string they're
    # passed. Billing callers (billing/router.py, agents/router.py) pass the authenticated
    # `tenant`, which is what makes the subject tamper-proof. team_billing.py deliberately keys
    # these by team member/user id instead (a team's plan comes from whichever member holds the
    # sub) -- that's a separate concern, not a BOLA. Unifying the team-vs-tenant subscription
    # subject is a future cleanup, tracked separately; do not change team_billing.py as part of
    # this fix.
    def status(self, customer_id: str) -> Subscription | None:
        return self.store.get(customer_id)

    def summary(self) -> dict:
        """Active-subscription counts overall and per plan (for the admin overview)."""
        active = [s for s in self.store.all() if s.status == "active"]
        by_plan: dict[str, int] = {}
        for s in active:
            by_plan[s.plan] = by_plan.get(s.plan, 0) + 1
        return {"active_subscriptions": len(active), "by_plan": by_plan}

    def cancel(self, customer_id: str) -> Subscription:
        sub = self.store.get(customer_id)
        if sub is None:
            raise KeyError(customer_id)
        if sub.stripe_subscription_id:
            self.gateway.cancel_subscription(stripe_subscription_id=sub.stripe_subscription_id)
        sub.cancel_at_period_end = True  # stays active until period end
        self.store.put(sub)
        return sub

    def resume(self, customer_id: str) -> Subscription:
        sub = self.store.get(customer_id)
        if sub is None:
            raise KeyError(customer_id)
        if sub.status != "active":
            raise ValueError("cannot resume a canceled subscription")
        if sub.stripe_subscription_id:
            self.gateway.resume_subscription(stripe_subscription_id=sub.stripe_subscription_id)
        sub.cancel_at_period_end = False
        self.store.put(sub)
        return sub

    def plan_for(self, customer_id: str) -> Plan:
        sub = self.store.get(customer_id)
        return get_plan(sub.plan if sub else "free")
