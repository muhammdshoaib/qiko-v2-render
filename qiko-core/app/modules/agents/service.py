"""Agent (worker) lifecycle: create -> training -> ready, tenant-scoped, gated by plan limits.

An agent here is the customer-facing configured instance; it runs on the reusable worker template
(app/modules/workers). Creating one is gated by the tenant's subscription worker_limit. Persists to
Postgres via AgentStore when USE_DB_STORES is on, so created workers survive a redeploy; in-memory
otherwise (dev/tests).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.modules.billing.plans import Plan, can_create_worker


AGENT_TYPES = {"worker", "pre_sales_writer", "sales_intelligence", "finance"}
AGENT_STATUSES = {"training", "ready"}


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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AgentStore(Protocol):
    async def add(self, agent: Agent) -> Agent: ...
    async def list(self, tenant: str) -> list[Agent]: ...
    async def count(self, tenant: str) -> int: ...
    async def get(self, tenant: str, agent_id: str) -> Agent | None: ...
    async def mark_ready(self, tenant: str, agent_id: str) -> Agent: ...
    async def update_config(self, tenant: str, agent_id: str, patch: dict) -> Agent: ...


@dataclass
class InMemoryAgentStore:
    _by_tenant: dict[str, list[Agent]] = field(default_factory=dict)

    async def add(self, agent: Agent) -> Agent:
        self._by_tenant.setdefault(agent.tenant, []).append(agent)
        return agent

    async def list(self, tenant: str) -> list[Agent]:
        return list(self._by_tenant.get(tenant, []))

    async def count(self, tenant: str) -> int:
        return len(self._by_tenant.get(tenant, []))

    async def get(self, tenant: str, agent_id: str) -> Agent | None:
        return next((a for a in self._by_tenant.get(tenant, []) if a.id == agent_id), None)

    async def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        for a in self._by_tenant.get(tenant, []):
            if a.id == agent_id:
                a.status = "ready"
                return a
        raise KeyError(agent_id)

    async def update_config(self, tenant: str, agent_id: str, patch: dict) -> Agent:
        for a in self._by_tenant.get(tenant, []):
            if a.id == agent_id:
                a.config = {**a.config, **patch}
                return a
        raise KeyError(agent_id)


@dataclass
class AgentService:
    store: AgentStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryAgentStore()

    async def count(self, tenant: str) -> int:
        return await self.store.count(tenant)

    async def list(self, tenant: str) -> list[Agent]:
        return await self.store.list(tenant)

    async def get(self, tenant: str, agent_id: str) -> Agent | None:
        return await self.store.get(tenant, agent_id)

    async def create(self, tenant: str, name: str, plan: Plan, *, atype: str = "worker",
                      config: dict | None = None) -> Agent:
        if not can_create_worker(await self.count(tenant), plan):
            raise PlanLimitError(f"plan '{plan.name}' allows {plan.worker_limit} worker(s)")
        agent = Agent(id=uuid.uuid4().hex[:12], tenant=tenant, name=name, atype=atype, config=config or {})
        return await self.store.add(agent)

    async def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        return await self.store.mark_ready(tenant, agent_id)

    async def update_config(self, tenant: str, agent_id: str, patch: dict) -> Agent:
        """Merge-patch the agent's free-form config (e.g. Background/Tone wizard fields)."""
        return await self.store.update_config(tenant, agent_id, patch)
