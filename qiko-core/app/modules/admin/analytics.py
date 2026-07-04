"""Dashboard revenue analytics: the report layer over the single-source revenue_metrics.

Adds period-over-period % change, top customers and a customer-revenue table on top of the base
MRR/ARPU/plan-distribution (which is NOT re-derived here - it comes from admin.metrics).
"""
from __future__ import annotations

from app.modules.admin.metrics import Subscription, revenue_metrics
from app.modules.billing.webhook import Invoice


def period_change_pct(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current else 0.0
    return round((current - previous) / previous * 100, 2)


def top_customers(invoices: list[Invoice], *, n: int = 5) -> list[dict]:
    totals: dict[str, int] = {}
    for inv in invoices:
        if inv.status == "paid":
            totals[inv.customer_id] = totals.get(inv.customer_id, 0) + inv.amount_cents
    ranked = sorted(totals.items(), key=lambda p: p[1], reverse=True)[:n]
    return [{"customer_id": c, "paid_cents": amt} for c, amt in ranked]


def revenue_report(subs: list[Subscription], invoices: list[Invoice], *, previous_mrr_cents: float = 0.0) -> dict:
    base = revenue_metrics(subs)  # single source of truth for MRR/ARPU/plan_distribution
    return {
        **base,
        "mrr_change_pct": period_change_pct(base["mrr_cents"], previous_mrr_cents),
        "top_customers": top_customers(invoices),
        "paid_invoice_total_cents": sum(i.amount_cents for i in invoices if i.status == "paid"),
    }
