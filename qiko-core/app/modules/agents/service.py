"""Agent (worker) lifecycle: create -> training -> ready, tenant-scoped, gated by plan limits.

An agent here is the customer-facing configured instance; it runs on the reusable worker template
(app/modules/workers). Creating one is gated by the tenant's subscription worker_limit. Persists to
Postgres via AgentStore when USE_DB_STORES is on, so created workers survive a redeploy; in-memory
otherwise (dev/tests).
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit_service
from app.modules.billing.plans import Plan


AGENT_TYPES = {"worker", "pre_sales_writer", "sales_intelligence", "finance", "intelligence"}
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


def build_worker_created_audit_row(*, tenant: str, worker_id: str, worker_type: str,
                                   status: str, source: str) -> dict:
    """Build a minimal creation event without copying worker or account content."""
    return audit_service.build_row(audit_service.AuditEvent(
        action=audit_actions.WORKER_CREATED,
        target_id=worker_id,
        tenant_id=tenant,
        actor_type=audit_service.SYSTEM,
        metadata={"source": source, "type": worker_type, "status": status},
    ))


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
    async def add(self, agent: Agent, *, audit: dict | None = None) -> Agent: ...
    async def add_with_limit(self, agent: Agent, worker_limit: int, *,
                             audit: dict | None = None) -> Agent: ...
    async def list(self, tenant: str) -> list[Agent]: ...
    async def count(self, tenant: str) -> int: ...
    async def get(self, tenant: str, agent_id: str) -> Agent | None: ...
    async def get_by_id(self, agent_id: str) -> Agent | None: ...
    # Cross-tenant: the platform-admin worker directory ONLY. Every tenant-facing caller uses list().
    async def list_all(self) -> list[Agent]: ...
    async def mark_ready(self, tenant: str, agent_id: str) -> Agent: ...
    # Any allowed status, unlike mark_ready which is one-way to "ready". Nothing could move a worker
    # back to training after a bad ingest.
    async def set_status(self, tenant: str, agent_id: str, status: str) -> Agent | None: ...
    # `audit` receives the config as it was under the row lock and returns the audit row to write in
    # the same transaction. See SqlAgentStore.update_config for why it is a callback.
    async def update_config(self, tenant: str, agent_id: str, patch: dict, *,
                            audit: Callable[[dict], dict] | None = None) -> Agent: ...
    async def set_enabled(self, tenant: str, agent_id: str, enabled: bool, *,
                          changed_by_email: str, reason: str | None) -> Agent: ...
    async def list_state_audit(self, tenant: str, *, limit: int = 50) -> list[AgentStateAudit]: ...


@dataclass
class InMemoryAgentStore:
    _by_tenant: dict[str, list[Agent]] = field(default_factory=dict)
    _audit: list[AgentStateAudit] = field(default_factory=list)
    # Where a same-transaction audit row goes when there is no transaction. Wired to the in-memory
    # audit store in main.py so dev and tests see the same rows production would write.
    audit_store: object | None = None
    _limit_locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    async def add(self, agent: Agent, *, audit: dict | None = None) -> Agent:
        agents = self._by_tenant.setdefault(agent.tenant, [])
        agents.append(agent)
        try:
            if audit is not None:
                if self.audit_store is None:
                    raise RuntimeError("worker creation audit store is not configured")
                self.audit_store.add_in(None, audit)
        except Exception:
            agents.pop()
            if not agents:
                self._by_tenant.pop(agent.tenant, None)
            raise
        return agent

    async def add_with_limit(self, agent: Agent, worker_limit: int, *,
                             audit: dict | None = None) -> Agent:
        lock = self._limit_locks.setdefault(agent.tenant, asyncio.Lock())
        async with lock:
            if worker_limit >= 0 and await self.count(agent.tenant) >= worker_limit:
                raise PlanLimitError(f"worker limit {worker_limit} reached")
            return await self.add(agent, audit=audit)

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

    async def set_status(self, tenant: str, agent_id: str, status: str) -> Agent | None:
        for a in self._by_tenant.get(tenant, []):
            if a.id == agent_id:
                a.status = status
                return a
        return None

    async def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        for a in self._by_tenant.get(tenant, []):
            if a.id == agent_id:
                a.status = "ready"
                return a
        raise KeyError(agent_id)

    async def update_config(self, tenant: str, agent_id: str, patch: dict, *,
                            audit: Callable[[dict], dict] | None = None) -> Agent:
        for a in self._by_tenant.get(tenant, []):
            if a.id == agent_id:
                # Snapshot BEFORE the merge. This store hands back live objects, so a caller that read
                # the agent first held a reference this line then mutated.
                previous = dict(a.config or {})
                a.config = {**a.config, **patch}
                if audit is not None and self.audit_store is not None:
                    self.audit_store.add_in(None, audit(previous))
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
        # And into the unified stream, mirroring what the SQL store writes inside its transaction. Both
        # here for the same reason as there: without it, "one stream" would be true in production and
        # false in every test.
        if self.audit_store is not None:
            from app.db.stores import _worker_availability_row

            self.audit_store.add_in(None, _worker_availability_row(
                tenant=tenant, agent_id=agent_id, name=agent.name,
                changed_by_email=changed_by_email, previous=previous, enabled=enabled,
                reason=(reason or "").strip() or None))
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
        audit_row = build_worker_created_audit_row(
            tenant=tenant,
            worker_id=agent.id,
            worker_type=agent.atype,
            status=agent.status,
            source="agents_api",
        )
        try:
            # Standalone in-memory services used by unit tests have no audit sink. The application
            # wires one before handling requests; SQL writes the row directly in add_with_limit.
            if isinstance(self.store, InMemoryAgentStore) and self.store.audit_store is None:
                return await self.store.add_with_limit(agent, plan.worker_limit)
            return await self.store.add_with_limit(agent, plan.worker_limit, audit=audit_row)
        except PlanLimitError as exc:
            raise PlanLimitError(f"plan '{plan.name}' allows {plan.worker_limit} worker(s)") from exc

    async def set_status(self, tenant: str, agent_id: str, status: str) -> Agent | None:
        """Set an agent's lifecycle status to any allowed value.

        mark_ready is one-way and hardcodes "ready", so nothing in the platform could move a worker
        back to training after a bad ingest. The status set is asserted here as well as at the HTTP
        boundary, so an internal caller cannot write a value the rest of the code does not understand.
        """
        if status not in AGENT_STATUSES:
            raise ValueError(f"unknown agent status: {status}")
        return await self.store.set_status(tenant, agent_id, status)

    async def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        return await self.store.mark_ready(tenant, agent_id)

    async def update_config(self, tenant: str, agent_id: str, patch: dict, *,
                            audit: Callable[[dict], dict] | None = None) -> Agent:
        """Merge-patch the agent's free-form config (e.g. Background/Tone wizard fields)."""
        return await self.store.update_config(tenant, agent_id, patch, audit=audit)

    async def set_enabled(self, tenant: str, agent_id: str, enabled: bool, *,
                          changed_by_email: str, reason: str | None = None) -> Agent:
        return await self.store.set_enabled(
            tenant, agent_id, enabled, changed_by_email=changed_by_email, reason=reason)

    async def list_state_audit(self, tenant: str, *, limit: int = 50) -> list[AgentStateAudit]:
        return await self.store.list_state_audit(tenant, limit=limit)
