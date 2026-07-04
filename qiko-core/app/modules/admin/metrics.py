"""Revenue analytics from a SINGLE source of truth.

In V1 revenue was reconciled across two databases; here every metric is computed from one list of
subscription records (the unified billing tables), so MRR/ARPU always agree with Stripe.
Monthly-equivalent revenue normalises annual plans to a monthly figure.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subscription:
    customer_id: str
    plan: str
    price_cents: int
    interval: str = "month"   # month | year
    status: str = "active"    # active | canceled | past_due


def _monthly_cents(sub: Subscription) -> float:
    return sub.price_cents / 12 if sub.interval == "year" else float(sub.price_cents)


def revenue_metrics(subs: list[Subscription]) -> dict:
    active = [s for s in subs if s.status == "active"]
    mrr_cents = sum(_monthly_cents(s) for s in active)
    plan_distribution: dict[str, int] = {}
    for s in active:
        plan_distribution[s.plan] = plan_distribution.get(s.plan, 0) + 1
    active_count = len(active)
    return {
        "mrr_cents": round(mrr_cents, 2),
        "active_subscriptions": active_count,
        "arpu_cents": round(mrr_cents / active_count, 2) if active_count else 0.0,
        "plan_distribution": plan_distribution,
    }
