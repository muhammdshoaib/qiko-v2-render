"""Agent (worker) lifecycle: create -> training -> ready, tenant-scoped, gated by plan limits.

An agent here is the customer-facing configured instance; it runs on the reusable worker template
(app/modules/workers). Creating one is gated by the tenant's subscription worker_limit. Persists to
Postgres via AgentStore when USE_DB_STORES is on, so created workers survive a redeploy; in-memory
otherwise (dev/tests).
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.modules.billing.plans import Plan


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
    enabled: bool = True


@dataclass(frozen=True)
class AgentStateAudit:
    id: int | None
    tenant: str
    agent_id: str
    changed_by_email: str
    previous_enabled: bool
    enabled: bool
    reason: str | None
    created_at: datetime


class AgentStore(Protocol):
    async def add(self, agent: Agent) -> Agent: ...
    async def add_with_limit(self, agent: Agent, worker_limit: int) -> Agent: ...
    async def list(self, tenant: str) -> list[Agent]: ...
    async def count(self, tenant: str) -> int: ...
    async def get(self, tenant: str, agent_id: str) -> Agent | None: ...
    async def get_by_id(self, agent_id: str) -> Agent | None: ...
    # Cross-tenant: the platform-admin worker directory ONLY. Every tenant-facing caller uses list().
    async def list_all(self) -> list[Agent]: ...
    async def mark_ready(self, tenant: str, agent_id: str) -> Agent: ...
    async def update_config(self, tenant: str, agent_id: str, patch: dict) -> Agent: ...
    async def set_enabled(self, tenant: str, agent_id: str, enabled: bool, *,
                          changed_by_email: str, reason: str | None) -> Agent: ...
    async def list_state_audit(self, tenant: str, *, limit: int = 50) -> list[AgentStateAudit]: ...


@dataclass
class InMemoryAgentStore:
    _by_tenant: dict[str, list[Agent]] = field(default_factory=dict)
    _audit: list[AgentStateAudit] = field(default_factory=list)
    _limit_locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    async def add(self, agent: Agent) -> Agent:
        self._by_tenant.setdefault(agent.tenant, []).append(agent)
        return agent

    async def add_with_limit(self, agent: Agent, worker_limit: int) -> Agent:
        lock = self._limit_locks.setdefault(agent.tenant, asyncio.Lock())
        async with lock:
            if worker_limit >= 0 and await self.count(agent.tenant) >= worker_limit:
                raise PlanLimitError(f"worker limit {worker_limit} reached")
            return await self.add(agent)

    async def list(self, tenant: str) -> list[Agent]:
        return list(self._by_tenant.get(tenant, []))

    async def list_all(self) -> list[Agent]:
        # Cross-tenant: platform-admin worker directory only. Sorted to match the SQL store.
        return sorted((a for agents in self._by_tenant.values() for a in agents),
                      key=lambda agent: (agent.tenant, agent.id))

    async def count(self, tenant: str) -> int:
        return len(self._by_tenant.get(tenant, []))

    async def get(self, tenant: str, agent_id: str) -> Agent | None:
        return next((a for a in self._by_tenant.get(tenant, []) if a.id == agent_id), None)

    async def get_by_id(self, agent_id: str) -> Agent | None:
        # Global (tenant-agnostic) lookup for the PUBLIC chat path only (worker ids are globally
        # unique). Callers must gate on status == "ready" and expose only public fields.
        for agents in self._by_tenant.values():
            for a in agents:
                if a.id == agent_id:
                    return a
        return None

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

    async def set_enabled(self, tenant: str, agent_id: str, enabled: bool, *,
                          changed_by_email: str, reason: str | None) -> Agent:
        agent = await self.get(tenant, agent_id)
        if agent is None:
            raise KeyError(agent_id)
        if agent.enabled == enabled:
            return agent
        previous = agent.enabled
        agent.enabled = enabled
        self._audit.append(AgentStateAudit(
            id=len(self._audit) + 1, tenant=tenant, agent_id=agent_id,
            changed_by_email=changed_by_email, previous_enabled=previous,
            enabled=enabled, reason=(reason or "").strip() or None,
            created_at=datetime.now(timezone.utc)))
        return agent

    async def list_state_audit(self, tenant: str, *, limit: int = 50) -> list[AgentStateAudit]:
        rows = [entry for entry in self._audit if entry.tenant == tenant]
        return list(reversed(rows[-max(1, min(limit, 200)):]))


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

    async def list_all(self) -> list[Agent]:
        # Cross-tenant: platform-admin worker directory only.
        return await self.store.list_all()

    async def get(self, tenant: str, agent_id: str) -> Agent | None:
        return await self.store.get(tenant, agent_id)

    async def get_by_id(self, agent_id: str) -> Agent | None:
        return await self.store.get_by_id(agent_id)

    async def create(self, tenant: str, name: str, plan: Plan, *, atype: str = "worker",
                      config: dict | None = None) -> Agent:
        agent = Agent(id=uuid.uuid4().hex[:12], tenant=tenant, name=name, atype=atype, config=config or {})
        try:
            return await self.store.add_with_limit(agent, plan.worker_limit)
        except PlanLimitError as exc:
            raise PlanLimitError(f"plan '{plan.name}' allows {plan.worker_limit} worker(s)") from exc

    async def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        return await self.store.mark_ready(tenant, agent_id)

    async def update_config(self, tenant: str, agent_id: str, patch: dict) -> Agent:
        """Merge-patch the agent's free-form config (e.g. Background/Tone wizard fields)."""
        return await self.store.update_config(tenant, agent_id, patch)

    async def set_enabled(self, tenant: str, agent_id: str, enabled: bool, *,
                          changed_by_email: str, reason: str | None = None) -> Agent:
        return await self.store.set_enabled(
            tenant, agent_id, enabled, changed_by_email=changed_by_email, reason=reason)

    async def list_state_audit(self, tenant: str, *, limit: int = 50) -> list[AgentStateAudit]:
        return await self.store.list_state_audit(tenant, limit=limit)
