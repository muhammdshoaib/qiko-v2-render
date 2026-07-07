"""Subscription plans and worker-limit gating. A worker_limit of -1 means unlimited.

Internal keys ("free"/"pro"/"enterprise") are kept stable for backward compatibility (existing
Stripe price mappings, tests, stored subscriptions); display_name/price/features are aligned to
the real product (verified live on stage-app.qiko.ai/app/pricing): Basic (contact sales, no
self-serve workers), Premium ($49/mo, 3 workers), Enterprise (custom, everything in Premium plus
custom model/on-prem/GGUF export/dedicated account manager).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Plan:
    name: str
    price_cents: int
    worker_limit: int
    display_name: str = ""
    features: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.display_name:
            object.__setattr__(self, "display_name", self.name.capitalize())


PLANS: dict[str, Plan] = {
    # Not a real self-serve tier on the live product (Basic there is "contact sales", no worker
    # count shown) -- kept as a 1-worker trial here so the existing signup/onboarding flow (every
    # new tenant starts on "free") still lets a new user build and try one worker before paying.
    "free": Plan("free", 0, 1, display_name="Basic", features=[
        "1 Digital Worker (trial)", "Contact sales for more",
    ]),
    "pro": Plan("pro", 4900, 3, display_name="Premium", features=[
        "3 Digital Workers", "Unlimited chats", "Unlimited training rules",
        "Knowledge Base Auto-Learning", "Calendly Scheduling Integration",
        "Voice Call Enablement", "Website Chat Embed", "Custom Knowledge Training",
    ]),
    "enterprise": Plan("enterprise", -1, -1, display_name="Enterprise", features=[
        "Everything in Premium", "Custom Model Build (IP Owned)",
        "Data Tagging and Pipeline Build", "On-Prem Deployment",
        "Full Model Export (GGUF)", "Dedicated Account Manager",
    ]),  # price_cents=-1 means "Custom Pricing", worker_limit=-1 means unlimited
}


def get_plan(name: str) -> Plan:
    return PLANS.get(name, PLANS["free"])


def list_plans() -> list[Plan]:
    return [PLANS["pro"], PLANS["enterprise"]]  # Basic is contact-sales-only, not shown as a self-serve tier


def can_create_worker(current_count: int, plan: Plan) -> bool:
    if plan.worker_limit < 0:
        return True
    return current_count < plan.worker_limit
