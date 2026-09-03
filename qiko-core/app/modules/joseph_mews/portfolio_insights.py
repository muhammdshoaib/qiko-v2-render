"""AI-generated per-property portfolio insights (JM2-1042 V1, built 2 Sep ahead of the AI
use-case workshop - see JM2/2026-09-02-portfolio-insights-workshop-prep.md for the design and
what is deliberately deferred to the workshop).

Investor-facing (unlike signal_summary.py's admin-facing output), so this deliberately produces
LESS than that module does: a single grounded observation, no suggested action - nothing that
could read as investment advice. Grounded ONLY in the yield/capital-growth/cash-flow figures
already shown on the property screen (jm-backend's portfolio_math.py); mortgage schedules and
forward projections are excluded from the facts sent here, not just asked to be ignored, so a
model cannot reference them even by accident.

Same shape as signal_summary.py on purpose (JSON-only system prompt, prefill, Pydantic
validation, bounded retry, never raises) and the same shared agent_id/tenant binding ("same
worker, same config, one cost bucket").
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.tenancy import reset_tenant, set_tenant
from app.modules.ai import usage
from app.modules.ai.gateway import LLMProvider
from app.modules.joseph_mews.guardrails import resolve_guardrails
from app.modules.joseph_mews.worker import AGENT_ID, TENANT

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_MAX_ATTEMPTS = 2

# Fixed, not admin-editable: this is the one thing that must never depend on whatever an admin
# has set as this Agent's Rules/Guardrails in Creator (JM2-1042's "no advice" decision is a
# product safety constraint, not a tone preference).
_NO_ADVICE_CONSTRAINT = (
    "Do not suggest any action, recommendation, or next step - observational commentary only, "
    "nothing that could be read as investment advice. Do not mention mortgage details or any "
    "forward-looking projection; only the current yield, capital growth, and cash flow figures "
    "supplied below."
)


def _build_system_prompt(agent_config: dict | None) -> str:
    # Rebuilt per call (not a module constant) so an edit to the Agent's Rules/Guardrails in the
    # Creator UI takes effect on the next request, no redeploy needed.
    return (
        "You are drafting a single one-sentence observation for a property investor about ONE "
        "of their properties, to show them in their investment app.\n\n"
        + resolve_guardrails(agent_config) + "\n\n" + _NO_ADVICE_CONSTRAINT + "\n\n"
        "Return ONLY a JSON object (no prose, no markdown fences) with exactly these keys:\n"
        '"summary": ONE sentence, grounded only in the supplied data, comparing or highlighting '
        "one of the supplied figures (e.g. against the investor's portfolio average, or its own "
        "trend).\n"
        '"groundedIn": a JSON array of dotted field paths (e.g. "property.grossYieldPct") for '
        "every fact the summary actually relies on."
    )


class PropertyInsightRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    requestId: str
    investor: dict = {}
    property: dict
    portfolioAverages: dict = {}
    locale: str = "en-GB"


class PropertyInsightResult(BaseModel):
    summary: str
    groundedIn: list[str] = []


class _ExtractedInsight(BaseModel):
    summary: str = ""
    groundedIn: list[str] = []


def _parse_llm_json_object(text: str) -> dict:
    match = _JSON_OBJECT.search(text)
    return json.loads(match.group(0) if match else text)


def _context_block(request: PropertyInsightRequest) -> str:
    parts = [f"property: {json.dumps(request.property)}"]
    if request.investor:
        parts.append(f"investor: {json.dumps(request.investor)}")
    if request.portfolioAverages:
        parts.append(f"portfolioAverages: {json.dumps(request.portfolioAverages)}")
    return "\n".join(parts)


def generate_property_insight(
    request: PropertyInsightRequest, provider: LLMProvider, agent_config: dict | None = None,
) -> PropertyInsightResult | None:
    """Best-effort: returns None (never raises) on a malformed or empty response after
    _MAX_ATTEMPTS - jm-backend caches nothing on failure and just omits the insight, matching
    signal_summary.py's failure shape.

    agent_config is the joseph-mews Creator Agent's config dict (None if not yet provisioned),
    used only to resolve the current Rules/Guardrails/Prompts for this call - see guardrails.py."""
    prompt = _context_block(request)
    system = _build_system_prompt(agent_config)
    agent_token = usage.set_agent(AGENT_ID)
    tenant_token = set_tenant(TENANT)
    try:
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                response = provider.generate(prompt, system=system, temperature=0.0, prefill="{")
                raw = _parse_llm_json_object(response.text)
                extracted = _ExtractedInsight.model_validate(raw)
            except (json.JSONDecodeError, ValidationError, AttributeError):
                continue
            if not extracted.summary.strip():
                continue
            return PropertyInsightResult(
                summary=extracted.summary.strip(), groundedIn=extracted.groundedIn,
            )
        return None
    finally:
        usage.reset_agent(agent_token)
        reset_tenant(tenant_token)
