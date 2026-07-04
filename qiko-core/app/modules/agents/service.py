"""Agent (worker) lifecycle: create -> training -> ready, tenant-scoped, gated by plan limits.

An agent here is the customer-facing configured instance; it runs on the reusable worker template
(app/modules/workers). Creating one is gated by the tenant's subscription worker_limit.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.modules.billing.plans import Plan, can_create_worker


class PlanLimitError(Exception):
    pass


@dataclass
class Agent:
    id: str
    tenant: str
    name: str
    atype: str = "worker"
    status: str = "training"  # training -> ready
    config: dict = field(default_factory=dict)


@dataclass
class AgentService:
    _by_tenant: dict[str, list[Agent]] = field(default_factory=dict)

    def count(self, tenant: str) -> int:
        return len(self._by_tenant.get(tenant, []))

    def list(self, tenant: str) -> list[Agent]:
        return list(self._by_tenant.get(tenant, []))

    def get(self, tenant: str, agent_id: str) -> Agent | None:
        return next((a for a in self._by_tenant.get(tenant, []) if a.id == agent_id), None)

    def create(self, tenant: str, name: str, plan: Plan, *, atype: str = "worker", config: dict | None = None) -> Agent:
        if not can_create_worker(self.count(tenant), plan):
            raise PlanLimitError(f"plan '{plan.name}' allows {plan.worker_limit} worker(s)")
        agent = Agent(id=uuid.uuid4().hex[:12], tenant=tenant, name=name, atype=atype, config=config or {})
        self._by_tenant.setdefault(tenant, []).append(agent)
        return agent

    def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        for a in self._by_tenant.get(tenant, []):
            if a.id == agent_id:
                a.status = "ready"
                return a
        raise KeyError(agent_id)
