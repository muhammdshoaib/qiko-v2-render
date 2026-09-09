"""Investor activity tracking + intent signal generation (JM2-1131).

Per `JosephMews-Activity-Intent-Signals.pdf`: the mobile app syncs granular activity (screens,
property visits, calculator steps) directly to qiko-core, never through jm-backend or
joseph-mews-backend. Property identity is name/location/postcode only -- property_id,
development_id, document_id and route params must never appear anywhere in this module, in the
aggregated evidence, or in a generated signal, matching the client's own activity-tracking
identity rule.

This module is the AI-facing half only: aggregating stored events into evidence and turning that
evidence into intent signals. Storage itself is app.db.stores.SqlInvestorActivityStore /
app.db.models.InvestorActivityEvent; the router (activity_router.py) wires the two together.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.tenancy import reset_tenant, set_tenant
from app.modules.ai import usage
from app.modules.ai.gateway import LLMProvider
from app.modules.joseph_mews.guardrails import resolve_guardrails
from app.modules.joseph_mews.worker import AGENT_ID, TENANT

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_MAX_ATTEMPTS = 2

# Deterministic signal-eligibility guardrail: repeated engagement with a specific property or
# with the calculator is what the client actually wants treated as an intent signal ("viewing a
# property 10x = signal"); passive screen browsing alone, no matter how frequent, is explicitly
# not ("viewing documents 10x = not a signal") -- see the module-level PDF reference for the
# broader activity categories this mirrors. This is enforced BEFORE the LLM is ever called
# (generate_intent_signals below), not left to the model's judgment, so noise cannot manufacture
# a signal even if the model would otherwise be tempted to find a pattern in it. Thresholds are
# a documented starting point (same spirit as qualification.py's scoring weights), meant to be
# tuned once the client confirms real numbers, not a design that needs revisiting to change them.
MIN_PROPERTY_VISITS_FOR_SIGNAL = 3
MIN_CALCULATOR_VISITS_FOR_SIGNAL = 3


def has_signal_worthy_evidence(aggregated: dict) -> bool:
    """True if aggregated activity (the shape aggregate_activity returns) contains at least one
    property or calculator step engaged with often enough to be worth asking the model about.
    Screen visits are deliberately never considered on their own, at any count."""
    properties = aggregated.get("properties") or []
    if any(p.get("visitCount", 0) >= MIN_PROPERTY_VISITS_FOR_SIGNAL for p in properties):
        return True
    calculator_steps = aggregated.get("calculatorSteps") or {}
    return any(count >= MIN_CALCULATOR_VISITS_FOR_SIGNAL for count in calculator_steps.values())


@dataclass(frozen=True)
class ActivityEvent:
    """One granular activity event, already stripped of any property/development/document id by
    the caller -- this module never accepts or looks for one."""

    category: str
    label: str
    property_name: str | None = None
    location: str | None = None
    postcode: str | None = None
    occurred_at: datetime | None = None


class InvestorActivityStore(Protocol):
    async def record(
        self, tenant: str, investor_ref: str, *, category: str, label: str,
        property_name: str | None = None, location: str | None = None, postcode: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None: ...

    async def list_for_investor(self, tenant: str, investor_ref: str) -> list[ActivityEvent]: ...


@dataclass
class InMemoryInvestorActivityStore:
    """In-memory dev/test default -- same protocol as db.stores.SqlInvestorActivityStore, swapped
    in behind app.state.investor_activity by main.py when USE_DB_STORES is not set, matching every
    other domain store in this app (e.g. AgentService/AgentStore)."""

    _events: dict[tuple[str, str], list[ActivityEvent]] = field(default_factory=dict)

    async def record(
        self, tenant: str, investor_ref: str, *, category: str, label: str,
        property_name: str | None = None, location: str | None = None, postcode: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        key = (tenant, investor_ref)
        self._events.setdefault(key, []).append(ActivityEvent(
            category=category, label=label, property_name=property_name, location=location,
            postcode=postcode, occurred_at=occurred_at or datetime.now(UTC),
        ))

    async def list_for_investor(self, tenant: str, investor_ref: str) -> list[ActivityEvent]:
        return list(self._events.get((tenant, investor_ref), []))


def aggregate_activity(events: list[ActivityEvent]) -> dict:
    """Turns a raw event list into the counted evidence an admin (or the LLM below) actually
    needs: how many times each screen/step was visited, and how many times each *named* property
    (never by id) was visited. Property identity is the (name, location, postcode) triple, since
    two different developments could plausibly share a name alone."""
    screens: Counter[str] = Counter()
    calculator_steps: Counter[str] = Counter()
    properties: Counter[tuple[str, str | None, str | None]] = Counter()
    for event in events:
        if event.category == "screen":
            screens[event.label] += 1
        elif event.category == "calculator_step":
            calculator_steps[event.label] += 1
        elif event.category == "property_visit" and event.property_name:
            properties[(event.property_name, event.location, event.postcode)] += 1
    return {
        "screens": dict(screens),
        "calculatorSteps": dict(calculator_steps),
        "properties": [
            {"propertyName": name, "location": location, "postcode": postcode, "visitCount": count}
            for (name, location, postcode), count in properties.items()
        ],
    }


class IntentSignalRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    requestId: str
    investorRef: str
    activity: dict = {}
    investor: dict = {}
    locale: str = "en-GB"


class IntentSignal(BaseModel):
    signal: str
    strength: str
    evidence: str
    category: str | None = None


class IntentSignalResult(BaseModel):
    signals: list[IntentSignal] = []


class _ExtractedSignals(BaseModel):
    signals: list[IntentSignal] = []


def _parse_llm_json_object(text: str) -> dict:
    match = _JSON_OBJECT.search(text)
    return json.loads(match.group(0) if match else text)


def _build_system_prompt(agent_config: dict | None) -> str:
    return (
        "You turn an investor's aggregated app activity into intent signals for a property "
        "investment agent: what the behaviour suggests about their interest, and how strong "
        "that signal is.\n\n" + resolve_guardrails(agent_config) + "\n\n"
        "Only use the activity counts you are given. Never invent a property, location, or "
        "count that is not present in the supplied data.\n\n"
        'Return ONLY a JSON object (no prose, no markdown fences) with exactly one key, '
        '"signals": a JSON array, each item having exactly these keys:\n'
        '"signal": a short label (e.g. "Interested in Manchester property").\n'
        '"strength": one of "high", "medium", "low".\n'
        '"evidence": the specific activity fact(s) that drove this signal.\n'
        '"category": a short theme, e.g. "location_interest", "calculator_engagement", '
        '"screen_focus" (omit if none fits).\n'
        'If the activity is too sparse to support any signal, return {"signals": []}.'
    )


def generate_intent_signals(
    request: IntentSignalRequest, provider: LLMProvider, agent_config: dict | None = None,
) -> IntentSignalResult | None:
    """Best-effort, mirrors signal_summary.summarize_signal: never raises, returns None after
    _MAX_ATTEMPTS on a malformed/unusable response rather than surfacing a partial or invented
    result to the admin panel.

    Checks has_signal_worthy_evidence() first and skips the model call entirely when nothing
    clears it -- an empty signals list is the correct, honest answer for "activity too sparse",
    and never calling the model for it is strictly better than calling it and hoping the prompt's
    "if the activity is too sparse, return no signals" instruction is followed."""
    if not has_signal_worthy_evidence(request.activity):
        return IntentSignalResult(signals=[])
    prompt = json.dumps({"activity": request.activity, "investor": request.investor})
    system = _build_system_prompt(agent_config)
    agent_token = usage.set_agent(AGENT_ID)
    tenant_token = set_tenant(TENANT)
    try:
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                response = provider.generate(prompt, system=system, temperature=0.0, prefill="{")
                raw = _parse_llm_json_object(response.text)
                extracted = _ExtractedSignals.model_validate(raw)
            except (json.JSONDecodeError, ValidationError, AttributeError):
                continue
            return IntentSignalResult(signals=extracted.signals)
        return None
    finally:
        usage.reset_agent(agent_token)
        reset_tenant(tenant_token)
