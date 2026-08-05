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

# Bedrock on-demand rates in micro-USD per 1,000 tokens, keyed on the model id WITHOUT the
# geography prefix: BedrockProvider.model_id returns "eu.anthropic.claude-sonnet-4-5", so a table
# keyed on the prefixed form would silently never match and every call would cost zero.
#
# Money is integer micro-USD throughout. The codebase has no Numeric or Float column anywhere and
# stores money as integer cents elsewhere; floats accumulating over millions of calls drift.
_INPUT = "input"
_OUTPUT = "output"
MODEL_PRICES_MICRO_USD_PER_1K: dict[str, dict[str, int]] = {
    "anthropic.claude-sonnet-4-5": {_INPUT: 3000, _OUTPUT: 15000},
    "anthropic.claude-sonnet-4": {_INPUT: 3000, _OUTPUT: 15000},
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {_INPUT: 3000, _OUTPUT: 15000},
    "anthropic.claude-3-5-haiku-20241022-v1:0": {_INPUT: 800, _OUTPUT: 4000},
    "amazon.titan-embed-text-v2:0": {_INPUT: 20, _OUTPUT: 0},
    "amazon.nova-sonic-v1:0": {_INPUT: 3400, _OUTPUT: 13600},
}

# Geography prefixes used by Bedrock inference profiles (mirrors bedrock._PROFILES).
_GEO_PREFIXES = ("eu.", "us.", "jp.", "au.", "global.")


def base_model_id(model_id: str) -> str:
    for prefix in _GEO_PREFIXES:
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def cost_micro_usd(model_id: str, input_tokens: int, output_tokens: int) -> int:
    """Cost of one call, or 0 for a model with no published rate in the table.

    Returning 0 for an unknown model is deliberate: a missing rate must never break an answer. The
    event is still recorded with its token counts, so the spend can be priced retrospectively once
    the rate is added, and `unpriced_models` on the totals surfaces the gap instead of hiding it.
    """
    rates = MODEL_PRICES_MICRO_USD_PER_1K.get(base_model_id(model_id))
    if rates is None:
        return 0
    return round(input_tokens * rates[_INPUT] / 1000) + round(output_tokens * rates[_OUTPUT] / 1000)


@dataclass(frozen=True)
class UsageEvent:
    tenant: str | None
    agent_id: str | None
    model_id: str
    operation: str
    input_tokens: int
    output_tokens: int
    cost_micro_usd: int
    created_at: datetime
    priced: bool


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micro_usd: int = 0
    calls: int = 0
    unpriced_calls: int = 0


class UsageStore(Protocol):
    async def add_many(self, events: list[UsageEvent]) -> None: ...
    async def totals(self, tenant: str, *, start: datetime | None = None,
                     end: datetime | None = None) -> UsageTotals: ...
    async def totals_by_agent(self, tenant: str, *, start: datetime | None = None,
                              end: datetime | None = None) -> dict[str, UsageTotals]: ...
    async def daily(self, tenant: str, *, start: datetime | None = None,
                    end: datetime | None = None) -> dict[str, UsageTotals]: ...


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


def accumulate(events: list[UsageEvent]) -> UsageTotals:
    totals = UsageTotals()
    for event in events:
        totals.input_tokens += event.input_tokens
        totals.output_tokens += event.output_tokens
        totals.cost_micro_usd += event.cost_micro_usd
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

    base = base_model_id(model_id)
    event = UsageEvent(
        tenant=get_tenant(),
        agent_id=get_agent(),
        model_id=model_id,
        operation=operation,
        input_tokens=max(0, int(input_tokens or 0)),
        output_tokens=max(0, int(output_tokens or 0)),
        cost_micro_usd=cost_micro_usd(model_id, input_tokens or 0, output_tokens or 0),
        created_at=datetime.now(timezone.utc),
        priced=base in MODEL_PRICES_MICRO_USD_PER_1K,
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
