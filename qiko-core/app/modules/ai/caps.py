"""Admin-set AI cost caps, enforced platform-wide (QIK-522).

Design constraints that shaped this
-----------------------------------
A cap has to be checked before work is done, but it must not cost a database round trip per model
call: an answer performs a retrieval embedding, a generation and possibly retries, so a naive check
would multiply DB load by the number of model calls and put that latency in front of every reply.

So the check reads a SHORT-LIVED CACHED spend figure. That means a tenant can overshoot its cap by at
most the spend it accrues within the cache window, which is a deliberate trade: a cap that adds
hundreds of milliseconds to every answer would be turned off, and a cap that is slightly soft is worth
more than a cap nobody enables. The window is small and configurable, and the alert fires from the
same figure so it cannot silently lag behind the enforcement.

Precedence is most specific first: a worker cap overrides its tenant cap, which overrides the
platform default. A cap of 0 means "blocked", and a NEGATIVE cap means "explicitly unlimited", because
the alternative encoding (absent row means unlimited) cannot express "unlimited, and I meant it"
distinctly from "nobody has configured this yet".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

logger = logging.getLogger(__name__)

# Sentinel for the platform-wide default row.
PLATFORM = "*"
UNLIMITED = -1
DEFAULT_ALERT_PCT = 80


@dataclass(frozen=True)
class CostCap:
    tenant: str
    agent_id: str | None
    monthly_cap_nano_usd: int
    alert_threshold_pct: int
    updated_by_email: str | None
    updated_at: datetime

    @property
    def unlimited(self) -> bool:
        return self.monthly_cap_nano_usd < 0


class CostCapStore(Protocol):
    async def upsert(self, cap: CostCap) -> CostCap: ...
    async def delete(self, tenant: str, agent_id: str | None) -> None: ...
    async def list_all(self) -> list[CostCap]: ...


@dataclass
class InMemoryCostCapStore:
    _caps: dict[tuple[str, str | None], CostCap] = field(default_factory=dict)

    async def upsert(self, cap: CostCap) -> CostCap:
        self._caps[(cap.tenant, cap.agent_id)] = cap
        return cap

    async def delete(self, tenant: str, agent_id: str | None) -> None:
        self._caps.pop((tenant, agent_id), None)

    async def list_all(self) -> list[CostCap]:
        return sorted(self._caps.values(), key=lambda cap: (cap.tenant, cap.agent_id or ""))


@dataclass(frozen=True)
class CapDecision:
    allowed: bool
    cap: CostCap | None
    spent_nano_usd: int
    limit_nano_usd: int | None
    alerting: bool

    @property
    def used_pct(self) -> int | None:
        if not self.limit_nano_usd:
            return None
        return round(self.spent_nano_usd * 100 / self.limit_nano_usd)


def month_start(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def select_cap(caps: list[CostCap], tenant: str, agent_id: str | None) -> CostCap | None:
    """Most specific wins: this worker, then this tenant, then the platform default."""
    by_key = {(cap.tenant, cap.agent_id): cap for cap in caps}
    for key in ((tenant, agent_id), (tenant, None), (PLATFORM, None)):
        if key in by_key:
            return by_key[key]
    return None


@dataclass
class CostGuard:
    """Answers "may this tenant or worker spend more this month".

    Fails OPEN on any internal error. A cap is a cost control, not a correctness requirement: taking
    the platform down because the spend query failed would be a far worse outcome than briefly
    allowing spend above a cap.
    """

    caps: CostCapStore
    usage: object | None = None
    notifications: object | None = None
    cache_seconds: float = 30.0
    _cached_caps: tuple[float, list[CostCap]] | None = None
    _cached_spend: dict[str, tuple[float, int]] = field(default_factory=dict)
    _alerted: dict[str, str] = field(default_factory=dict)

    async def _load_caps(self) -> list[CostCap]:
        now = time.monotonic()
        if self._cached_caps and now - self._cached_caps[0] < self.cache_seconds:
            return self._cached_caps[1]
        caps = await self.caps.list_all()
        self._cached_caps = (now, caps)
        return caps

    async def _spend(self, tenant: str, agent_id: str | None, *, scoped_to_agent: bool) -> int:
        if self.usage is None:
            return 0
        key = f"{tenant}/{agent_id}" if scoped_to_agent else tenant
        now = time.monotonic()
        cached = self._cached_spend.get(key)
        if cached and now - cached[0] < self.cache_seconds:
            return cached[1]
        start = month_start()
        if scoped_to_agent:
            per_agent = await self.usage.totals_by_agent(tenant, start=start)
            spent = per_agent.get(agent_id or "unattributed")
            value = spent.cost_nano_usd if spent else 0
        else:
            value = (await self.usage.totals(tenant, start=start)).cost_nano_usd
        self._cached_spend[key] = (now, value)
        return value

    async def check(self, tenant: str, agent_id: str | None = None) -> CapDecision:
        try:
            cap = select_cap(await self._load_caps(), tenant, agent_id)
            if cap is None or cap.unlimited:
                return CapDecision(allowed=True, cap=cap, spent_nano_usd=0,
                                   limit_nano_usd=None, alerting=False)
            spent = await self._spend(tenant, agent_id,
                                      scoped_to_agent=cap.agent_id is not None)
            limit = cap.monthly_cap_nano_usd
            allowed = spent < limit
            alerting = limit > 0 and spent * 100 >= limit * cap.alert_threshold_pct
            decision = CapDecision(allowed=allowed, cap=cap, spent_nano_usd=spent,
                                   limit_nano_usd=limit, alerting=alerting)
            if alerting or not allowed:
                await self._alert(tenant, agent_id, decision)
            return decision
        except Exception as error:  # noqa: BLE001 - a cost control must never take the platform down
            logger.warning("cost cap check failed, allowing", extra={
                "tenant": tenant, "source": "ai.caps", "error": str(error)})
            return CapDecision(allowed=True, cap=None, spent_nano_usd=0,
                               limit_nano_usd=None, alerting=False)

    async def _alert(self, tenant: str, agent_id: str | None, decision: CapDecision) -> None:
        """One notification per state change per month, not one per request.

        Without the state key an admin would receive an alert on every single answer once a tenant
        crossed its threshold, which trains people to ignore the alerts entirely.
        """
        if self.notifications is None:
            return
        state = "exceeded" if not decision.allowed else "threshold"
        key = f"{tenant}/{agent_id or ''}/{month_start().date().isoformat()}"
        if self._alerted.get(key) == state:
            return
        self._alerted[key] = state
        used = decision.used_pct
        title = ("AI cost cap exceeded" if state == "exceeded"
                 else f"AI spend at {used}% of cap")
        try:
            await self.notifications.notify(
                tenant, type="ai_cost_cap", title=title,
                body=(f"Spend this month is {decision.spent_nano_usd / 1_000_000_000:.2f} USD "
                      f"against a cap of {(decision.limit_nano_usd or 0) / 1_000_000_000:.2f} USD."),
                agent_id=agent_id,
                metadata={"spent_nano_usd": decision.spent_nano_usd,
                          "limit_nano_usd": decision.limit_nano_usd, "state": state})
        except Exception as error:  # noqa: BLE001 - an alert failure must not block the answer
            logger.warning("cost cap alert failed", extra={
                "tenant": tenant, "source": "ai.caps", "error": str(error)})

    def invalidate(self) -> None:
        """Drop the caches so a newly saved cap applies immediately rather than after the window."""
        self._cached_caps = None
        self._cached_spend.clear()


class CostCapExceeded(Exception):
    """Raised when a worker is asked to do work its tenant can no longer pay for."""

    def __init__(self, decision: CapDecision) -> None:
        super().__init__("AI cost cap reached")
        self.decision = decision
