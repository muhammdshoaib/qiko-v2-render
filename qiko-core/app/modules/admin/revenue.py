"""Revenue report computed from the platform's own billing tables.

The earnings heuristic is: paid invoices count as recognized revenue, open invoices are
outstanding ARR, and active subscriptions give forward-looking MRR. All numbers come from the
same Postgres-backed billing tables that webhooks and reconciliation keep in sync.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.modules.billing.plans import PLANS
from app.modules.billing.webhook import Invoice


class InvoiceStore(Protocol):
    def list(self, customer_id: str | None = None) -> list[Invoice]: ...


class Subscription(Protocol):
    plan: str
    status: str


class SubscriptionStore(Protocol):
    def all(self) -> list[Subscription]: ...


@dataclass
class RevenueReport:
    total_paid_cents: int
    outstanding_cents: int
    mrr_cents: int
    arr_cents: int
    active_subscriptions: int
    by_plan: dict[str, int]
    monthly: list[dict]


def _month_key(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(timezone.utc).strftime("%Y-%m")
    return dt.strftime("%Y-%m")


def revenue_report(invoices: InvoiceStore, subscriptions: SubscriptionStore) -> RevenueReport:
    all_invoices = invoices.list()
    paid = [i for i in all_invoices if i.status == "paid"]
    open_ = [i for i in all_invoices if i.status == "open"]

    total_paid_cents = sum(i.amount_cents for i in paid)
    outstanding_cents = sum(i.amount_cents for i in open_)

    monthly: dict[str, int] = {}
    for i in paid:
        key = _month_key(i.period_start)
        monthly[key] = monthly.get(key, 0) + i.amount_cents
    sorted_monthly = [{"month": m, "paid_cents": c} for m, c in sorted(monthly.items())]

    active = [s for s in subscriptions.all() if s.status == "active"]
    active_subscriptions = len(active)
    by_plan: dict[str, int] = {}
    mrr_cents = 0
    for s in active:
        plan = PLANS.get(s.plan, PLANS["free"])
        price = plan.price_cents if plan.price_cents > 0 else 0
        mrr_cents += price
        by_plan[s.plan] = by_plan.get(s.plan, 0) + 1

    return RevenueReport(
        total_paid_cents=total_paid_cents,
        outstanding_cents=outstanding_cents,
        mrr_cents=mrr_cents,
        arr_cents=mrr_cents * 12,
        active_subscriptions=active_subscriptions,
        by_plan=by_plan,
        monthly=sorted_monthly,
    )


def revenue_report_dict(invoices: InvoiceStore, subscriptions: SubscriptionStore) -> dict:
    r = revenue_report(invoices, subscriptions)
    return {
        "total_paid_cents": r.total_paid_cents,
        "outstanding_cents": r.outstanding_cents,
        "mrr_cents": r.mrr_cents,
        "arr_cents": r.arr_cents,
        "active_subscriptions": r.active_subscriptions,
        "by_plan": r.by_plan,
        "monthly": r.monthly,
    }
