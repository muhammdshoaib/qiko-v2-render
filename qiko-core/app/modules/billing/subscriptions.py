"""Stripe subscription lifecycle over the plan catalog.

Stripe I/O sits behind a StripeGateway protocol so the lifecycle logic (checkout -> active ->
cancel-at-period-end -> resume) is testable without the network. A real StripeGateway (lazy
`stripe`) is used in prod; a fake drives the tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.billing.plans import Plan, get_plan


class StripeGateway(Protocol):
    def create_checkout_session(self, *, customer_id: str, price_id: str, promo: str | None,
                                client_reference_id: str | None = None) -> str: ...
    def billing_portal_url(self, *, customer_id: str) -> str: ...


@dataclass
class Subscription:
    customer_id: str
    plan: str
    status: str = "active"          # active | canceled
    cancel_at_period_end: bool = False


@dataclass
class SubscriptionService:
    gateway: StripeGateway
    # The subscription subject is the authenticated TENANT (matches agents-gating in
    # agents/router.py: `subs.status(tenant)`), so `_subs` is keyed by tenant.
    _subs: dict[str, Subscription] = field(default_factory=dict)
    # tenant -> real Stripe customer id ("cus_..."). Kept in-memory on purpose: subscriptions
    # here are already in-memory/non-durable and billing isn't wired to a live Stripe yet, so
    # there's nothing durable to map to. When billing goes live, `_subs` AND `_customers` should
    # become a durable (SQL) store together -- do not persist one without the other.
    _customers: dict[str, str] = field(default_factory=dict)

    def link_customer(self, tenant: str, stripe_customer_id: str) -> None:
        """Record the real Stripe customer id for a tenant (set from the webhook on checkout)."""
        self._customers[tenant] = stripe_customer_id

    def stripe_customer_ref(self, tenant: str) -> str:
        """The Stripe customer id linked to this tenant if known, else the tenant string itself
        as a stable client-reference until a real Stripe customer exists for it."""
        return self._customers.get(tenant, tenant)

    def start_checkout(self, tenant: str, plan_name: str, *, price_id: str, promo: str | None = None) -> str:
        get_plan(plan_name)  # validate plan exists
        # `client_reference_id=tenant` lets the checkout.session.completed webhook tie the created
        # Stripe customer back to our tenant (see webhook.py) -- the subject is never client input.
        return self.gateway.create_checkout_session(
            customer_id=self.stripe_customer_ref(tenant), price_id=price_id, promo=promo,
            client_reference_id=tenant)

    def activate(self, customer_id: str, plan_name: str) -> Subscription:
        """Called on checkout.session.completed (webhook) to mark the subscription active."""
        sub = Subscription(customer_id=customer_id, plan=plan_name, status="active")
        self._subs[customer_id] = sub
        return sub

    def portal_url(self, tenant: str) -> str:
        return self.gateway.billing_portal_url(customer_id=self.stripe_customer_ref(tenant))

    # NOTE: status/activate/cancel/resume/plan_for key `_subs` by whatever string they're passed.
    # Billing callers (billing/router.py, agents/router.py) pass the authenticated `tenant`, which
    # is what makes the subject tamper-proof. team_billing.py deliberately keys these by team
    # member/user id instead (a team's plan comes from whichever member holds the sub) -- that's a
    # separate concern, not a BOLA. Unifying the team-vs-tenant subscription subject is a future
    # cleanup, tracked separately; do not change team_billing.py as part of this fix.
    def status(self, customer_id: str) -> Subscription | None:
        return self._subs.get(customer_id)

    def summary(self) -> dict:
        """Active-subscription counts overall and per plan (for the admin overview)."""
        active = [s for s in self._subs.values() if s.status == "active"]
        by_plan: dict[str, int] = {}
        for s in active:
            by_plan[s.plan] = by_plan.get(s.plan, 0) + 1
        return {"active_subscriptions": len(active), "by_plan": by_plan}

    def cancel(self, customer_id: str) -> Subscription:
        sub = self._subs[customer_id]
        sub.cancel_at_period_end = True  # stays active until period end
        return sub

    def resume(self, customer_id: str) -> Subscription:
        sub = self._subs[customer_id]
        if sub.status != "active":
            raise ValueError("cannot resume a canceled subscription")
        sub.cancel_at_period_end = False
        return sub

    def plan_for(self, customer_id: str) -> Plan:
        sub = self._subs.get(customer_id)
        return get_plan(sub.plan if sub else "free")
