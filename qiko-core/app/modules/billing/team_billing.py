"""Team-scoped billing: a team's plan comes from whichever member holds the active subscription,
and the worker limit is enforced across the whole team's worker count (not per user)."""
from __future__ import annotations

from app.modules.billing.plans import Plan, get_plan
from app.modules.billing.subscriptions import SubscriptionService


def resolve_billing_user(members: list[str], subs: SubscriptionService) -> str | None:
    """The team's billing user = the first member with an active (non-cancelling) subscription."""
    for member in members:
        sub = subs.status(member)
        if sub and sub.status == "active" and not sub.cancel_at_period_end:
            return member
    return None


def team_plan(members: list[str], subs: SubscriptionService) -> Plan:
    billing_user = resolve_billing_user(members, subs)
    return subs.plan_for(billing_user) if billing_user else get_plan("free")


def can_team_create_worker(members: list[str], team_worker_count: int, subs: SubscriptionService) -> bool:
    plan = team_plan(members, subs)
    return plan.worker_limit < 0 or team_worker_count < plan.worker_limit
