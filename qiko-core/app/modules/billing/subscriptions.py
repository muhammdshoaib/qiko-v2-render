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
    def create_checkout_session(self, *, customer_id: str, price_id: str, promo: str | None) -> str: ...
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
    _subs: dict[str, Subscription] = field(default_factory=dict)

    def start_checkout(self, customer_id: str, plan_name: str, *, price_id: str, promo: str | None = None) -> str:
        get_plan(plan_name)  # validate plan exists
        return self.gateway.create_checkout_session(customer_id=customer_id, price_id=price_id, promo=promo)

    def activate(self, customer_id: str, plan_name: str) -> Subscription:
        """Called on checkout.session.completed (webhook) to mark the subscription active."""
        sub = Subscription(customer_id=customer_id, plan=plan_name, status="active")
        self._subs[customer_id] = sub
        return sub

    def portal_url(self, customer_id: str) -> str:
        return self.gateway.billing_portal_url(customer_id=customer_id)

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
