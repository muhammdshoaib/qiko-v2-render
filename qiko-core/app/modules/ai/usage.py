"""Per-tenant, per-worker AI token and cost accounting (QIK-514).

Why a context variable rather than arguments
--------------------------------------------
Every model call in the platform funnels through exactly two places: `BedrockProvider.generate`
for text and `TitanEmbeddings.embed` for vectors. Instrumenting there catches all ten
`provider.generate` call sites AND the retry loops inside the RFP pipeline, which a call-site
approach would undercount.

Both of those chokepoints are synchronous functions reached through `asyncio.to_thread`, sometimes
several frames below the code that knows the tenant. Threading a parameter down would mean changing
the `LLMProvider` protocol and every fake implementation in the test suite. Context variables are
copied into `asyncio.to_thread` workers, so a scope opened in the request path is visible at the
model call without touching a single signature. `app/core/tenancy.py` already establishes this
pattern for the tenant id.

Attribution honesty
-------------------
An event records the tenant and worker that were bound AT THE MOMENT OF THE CALL. Where nothing is
bound, the event is still recorded with a null tenant rather than dropped: silently losing spend is
worse than recording spend you have to go and attribute later.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Protocol

logger = logging.getLogger(__name__)

# Bedrock on-demand rates in NANO-USD per 1,000 tokens.
#
# Nano rather than micro because micro rounds real calls to zero. Titan v2 is 20 micro-USD per 1,000
# tokens, so an 8-token embedding costs 0.16 micro-USD and rounded away entirely -- and an ingest
# performs one embedding per chunk, so a whole corpus would have appeared free. Verified against live
# Bedrock: an 8-token embed recorded 0.
#
# Money stays an integer. The schema has no Numeric or Float column anywhere and money is integer
# cents elsewhere; a float accumulating over millions of calls drifts.
_INPUT = "input"
_OUTPUT = "output"
MODEL_PRICES_NANO_USD_PER_1K: dict[str, dict[str, int]] = {
    "anthropic.claude-sonnet-4-5": {_INPUT: 3_000_000, _OUTPUT: 15_000_000},
    "anthropic.claude-sonnet-4": {_INPUT: 3_000_000, _OUTPUT: 15_000_000},
    "anthropic.claude-3-5-sonnet": {_INPUT: 3_000_000, _OUTPUT: 15_000_000},
    "anthropic.claude-3-5-haiku": {_INPUT: 800_000, _OUTPUT: 4_000_000},
    "anthropic.claude-3-haiku": {_INPUT: 250_000, _OUTPUT: 1_250_000},
    "amazon.titan-embed-text-v2": {_INPUT: 20_000, _OUTPUT: 0},
    "amazon.nova-sonic": {_INPUT: 3_400_000, _OUTPUT: 13_600_000},
}

# Geography prefixes used by Bedrock inference profiles (mirrors bedrock._PROFILES).
_GEO_PREFIXES = ("eu.", "us.", "jp.", "au.", "global.")


def base_model_id(model_id: str) -> str:
    for prefix in _GEO_PREFIXES:
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def rates_for(model_id: str) -> dict[str, int] | None:
    """Longest-prefix match against the price table.

    Bedrock resolves to a DATE-AND-VERSION-QUALIFIED id: the configured
    "anthropic.claude-sonnet-4-5" actually invokes
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0". Exact-match lookup therefore failed on every real
    call and priced it at zero, which a live check caught. Prefix matching means a new dated revision
    of a known model is priced correctly on the day AWS ships it, rather than silently free.
    """
    base = base_model_id(model_id)
    matches = [key for key in MODEL_PRICES_NANO_USD_PER_1K if base.startswith(key)]
    if not matches:
        return None
    # Longest key wins, so claude-3-5-haiku never resolves against a shorter claude-3 entry.
    return MODEL_PRICES_NANO_USD_PER_1K[max(matches, key=len)]


def cost_nano_usd(model_id: str, input_tokens: int, output_tokens: int) -> int:
    """Cost of one call in nano-USD, or 0 for a model with no published rate.

    Returning 0 for an unknown model is deliberate: a missing rate must never break an answer. The
    event is still recorded with its token counts, so the spend can be priced retrospectively once
    the rate is added, and unpriced_calls on the totals surfaces the gap instead of hiding it.
    """
    rates = rates_for(model_id)
    if rates is None:
        return 0
    return (input_tokens * rates[_INPUT] + output_tokens * rates[_OUTPUT]) // 1000


@dataclass(frozen=True)
class UsageEvent:
    tenant: str | None
    agent_id: str | None
    model_id: str
    operation: str
    input_tokens: int
    output_tokens: int
    cost_nano_usd: int
    created_at: datetime
    priced: bool


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_nano_usd: int = 0
    calls: int = 0
    unpriced_calls: int = 0


class UsageStore(Protocol):
    async def add_many(self, events: list[UsageEvent]) -> None: ...
    # Cross-tenant: the platform AI-spend view ONLY. Separate methods rather than an optional
    # tenant=None argument, so an accidental omission cannot silently widen a tenant-scoped call.
    async def platform_totals(self, *, start: datetime | None = None,
                              end: datetime | None = None) -> UsageTotals: ...
    async def platform_by(self, dimension: str, *, start: datetime | None = None,
                          end: datetime | None = None) -> dict[str, UsageTotals]: ...
    async def platform_agent_usage(self, *, start: datetime | None = None,
                                   end: datetime | None = None) -> dict[str, AgentUsageSummary]: ...
    async def totals(self, tenant: str, *, start: datetime | None = None,
                     end: datetime | None = None) -> UsageTotals: ...
    async def totals_by_agent(self, tenant: str, *, start: datetime | None = None,
                              end: datetime | None = None) -> dict[str, UsageTotals]: ...
    async def daily(self, tenant: str, *, start: datetime | None = None,
                    end: datetime | None = None) -> dict[str, UsageTotals]: ...


@dataclass(frozen=True)
class AgentUsageSummary:
    """One worker's spend plus when it was last seen, for the monitoring view."""

    tenant: str | None
    agent_id: str | None
    totals: UsageTotals
    last_seen: datetime | None


def dimensions() -> dict:
    """The breakdowns the platform spend view offers. A dict rather than four methods so adding one
    is a single entry and the API surface does not grow a method per chart."""
    return _DIMENSIONS


_DIMENSIONS = {"tenant": lambda event: event.tenant or "unattributed",
               "model": lambda event: base_model_id(event.model_id),
               "operation": lambda event: event.operation,
               "day": lambda event: event.created_at.date().isoformat()}


@dataclass
class InMemoryUsageStore:
    events: list[UsageEvent] = field(default_factory=list)

    async def add_many(self, events: list[UsageEvent]) -> None:
        self.events.extend(events)

    def _in_window(self, tenant: str, start: datetime | None, end: datetime | None) -> list[UsageEvent]:
        return [e for e in self.events
                if e.tenant == tenant
                and (start is None or e.created_at >= start)
                and (end is None or e.created_at <= end)]

    async def totals(self, tenant: str, *, start: datetime | None = None,
                     end: datetime | None = None) -> UsageTotals:
        return accumulate(self._in_window(tenant, start, end))

    async def totals_by_agent(self, tenant: str, *, start: datetime | None = None,
                              end: datetime | None = None) -> dict[str, UsageTotals]:
        return group(self._in_window(tenant, start, end), lambda e: e.agent_id or "unattributed")

    async def daily(self, tenant: str, *, start: datetime | None = None,
                    end: datetime | None = None) -> dict[str, UsageTotals]:
        return group(self._in_window(tenant, start, end),
                     lambda e: e.created_at.date().isoformat())

    def _all_in_window(self, start, end) -> list[UsageEvent]:
        return [e for e in self.events
                if (start is None or e.created_at >= start) and (end is None or e.created_at <= end)]

    async def platform_totals(self, *, start=None, end=None) -> UsageTotals:
        return accumulate(self._all_in_window(start, end))

    async def platform_by(self, dimension: str, *, start=None, end=None) -> dict[str, UsageTotals]:
        return group(self._all_in_window(start, end), _DIMENSIONS[dimension])

    async def platform_agent_usage(self, *, start=None, end=None) -> dict[str, AgentUsageSummary]:
        return summarise_agents(self._all_in_window(start, end))


def accumulate(events: list[UsageEvent]) -> UsageTotals:
    totals = UsageTotals()
    for event in events:
        totals.input_tokens += event.input_tokens
        totals.output_tokens += event.output_tokens
        totals.cost_nano_usd += event.cost_nano_usd
        totals.calls += 1
        if not event.priced:
            totals.unpriced_calls += 1
    return totals


def group(events: list[UsageEvent], key) -> dict[str, UsageTotals]:
    buckets: dict[str, list[UsageEvent]] = {}
    for event in events:
        buckets.setdefault(key(event), []).append(event)
    return {name: accumulate(rows) for name, rows in sorted(buckets.items())}


# --- request/job scope --------------------------------------------------------------------------

_events: ContextVar[list[UsageEvent] | None] = ContextVar("ai_usage_events", default=None)
_agent: ContextVar[str | None] = ContextVar("ai_usage_agent", default=None)


def set_agent(agent_id: str | None) -> object:
    """Bind the worker that subsequent model calls should be attributed to."""
    return _agent.set(agent_id)


def reset_agent(token: object) -> None:
    _agent.reset(token)  # type: ignore[arg-type]


def get_agent() -> str | None:
    return _agent.get()


@contextmanager
def scope() -> Iterator[list[UsageEvent]]:
    """Collect the events produced inside this block.

    Nested scopes deliberately reuse the outer list: a job that opens a scope and then calls code
    which opens another must not have half its spend disappear into an inner list nobody flushes.
    """
    existing = _events.get()
    if existing is not None:
        yield existing
        return
    collected: list[UsageEvent] = []
    token = _events.set(collected)
    try:
        yield collected
    finally:
        _events.reset(token)


def record(model_id: str, operation: str, *, input_tokens: int, output_tokens: int = 0) -> UsageEvent:
    """Record one model call against whatever tenant and worker are currently bound."""
    from app.core.tenancy import get_tenant

    event = UsageEvent(
        tenant=get_tenant(),
        agent_id=get_agent(),
        model_id=model_id,
        operation=operation,
        input_tokens=max(0, int(input_tokens or 0)),
        output_tokens=max(0, int(output_tokens or 0)),
        cost_nano_usd=cost_nano_usd(model_id, input_tokens or 0, output_tokens or 0),
        created_at=datetime.now(timezone.utc),
        priced=rates_for(model_id) is not None,
    )
    collected = _events.get()
    if collected is None:
        # No scope open: the call still happened and still cost money, so say so rather than
        # dropping it. Paths that legitimately run outside a request should open a scope.
        logger.warning("ai usage recorded outside a scope", extra={
            "tenant": event.tenant, "source": "ai.usage",
            "model": event.model_id, "operation": operation})
        return event
    collected.append(event)
    return event


async def flush(store: UsageStore | None, events: list[UsageEvent]) -> None:
    """Persist collected events. Never raises: metering must not break a served answer."""
    if not store or not events:
        return
    try:
        await store.add_many(events)
    except Exception as error:  # noqa: BLE001 - accounting must not fail the request
        logger.warning("ai usage flush failed", extra={
            "source": "ai.usage", "error": str(error), "count": len(events)})


def summarise_agents(events: list[UsageEvent]) -> dict[str, AgentUsageSummary]:
    """Per-worker spend keyed "tenant/agent", including workers with no agent id.

    Unattributed spend gets its own bucket rather than being dropped, so the monitoring view's total
    always reconciles with the platform total.
    """
    buckets: dict[str, list[UsageEvent]] = {}
    for event in events:
        buckets.setdefault(f"{event.tenant or 'unattributed'}/{event.agent_id or 'unattributed'}",
                           []).append(event)
    summaries: dict[str, AgentUsageSummary] = {}
    for key, rows in sorted(buckets.items()):
        summaries[key] = AgentUsageSummary(
            tenant=rows[0].tenant, agent_id=rows[0].agent_id, totals=accumulate(rows),
            last_seen=max(row.created_at for row in rows))
    return summaries
