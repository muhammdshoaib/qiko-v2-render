"""Subscription plans and worker-limit gating. A worker_limit of -1 means unlimited."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    price_cents: int
    worker_limit: int


PLANS: dict[str, Plan] = {
    "free": Plan("free", 0, 1),
    "pro": Plan("pro", 5000, 5),
    "enterprise": Plan("enterprise", 50000, -1),  # unlimited
}


def get_plan(name: str) -> Plan:
    return PLANS.get(name, PLANS["free"])


def can_create_worker(current_count: int, plan: Plan) -> bool:
    if plan.worker_limit < 0:
        return True
    return current_count < plan.worker_limit
