"""AI-generated intent signal summaries (JM2-1065), contract confirmed on JM2-1066:
`.devin/ledger` -> JM2/api-spec-intent-signals-and-insights.md section 3.3.

jm-backend owns the IntentSignal row and calls this per newly created signal; this module only
drafts summary/suggestedNextAction from the structured facts jm-backend sends, it never touches
jm-backend's database. Field names mirror the contract's camelCase JSON directly (same convention
as app/modules/finance/schemas.py), not translated to snake_case and back.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.tenancy import reset_tenant, set_tenant
from app.modules.ai import usage
from app.modules.ai.gateway import LLMProvider
from app.modules.joseph_mews.guardrails import SHARED_GUARDRAILS
from app.modules.joseph_mews.worker import AGENT_ID, TENANT

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_MAX_ATTEMPTS = 2

SYSTEM = (
    "You are drafting a one-paragraph summary and a suggested next action for a property "
    "investment agent, describing why a specific investor's behaviour just triggered an intent "
    "signal.\n\n" + SHARED_GUARDRAILS + "\n\n"
    "Return ONLY a JSON object (no prose, no markdown fences) with exactly these keys:\n"
    '"summary": a 1-3 sentence, agent-facing summary of what the investor did and why it '
    "matters, grounded only in the supplied data.\n"
    '"suggestedNextAction": a short, concrete action for the agent to take next.\n'
    '"groundedIn": a JSON array of dotted field paths (e.g. "investor.investmentPreferences", '
    '"property.projectedGrossYield") for every fact the summary or action actually relies on.'
)


class _SignalContext(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int | None = None
    signalType: str = ""
    triggeringActivity: str = ""
    intentLevel: str = ""
    ruleName: str = ""
    ruleDescription: str = ""


class SignalSummarizeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    requestId: str
    signal: _SignalContext
    investor: dict = {}
    property: dict | None = None
    development: dict | None = None
    propertyUnit: dict | None = None
    locale: str = "en-GB"


class SignalSummaryResult(BaseModel):
    summary: str
    suggestedNextAction: str
    groundedIn: list[str] = []


class _ExtractedSummary(BaseModel):
    summary: str = ""
    suggestedNextAction: str = ""
    groundedIn: list[str] = []


def _parse_llm_json_object(text: str) -> dict:
    match = _JSON_OBJECT.search(text)
    return json.loads(match.group(0) if match else text)


def _context_block(request: SignalSummarizeRequest) -> str:
    parts = [f"signal: {request.signal.model_dump_json()}", f"investor: {json.dumps(request.investor)}"]
    if request.property is not None:
        parts.append(f"property: {json.dumps(request.property)}")
    if request.development is not None:
        parts.append(f"development: {json.dumps(request.development)}")
    if request.propertyUnit is not None:
        parts.append(f"propertyUnit: {json.dumps(request.propertyUnit)}")
    return "\n".join(parts)


def summarize_signal(request: SignalSummarizeRequest, provider: LLMProvider) -> SignalSummaryResult | None:
    """Best-effort: returns None (never raises) on a malformed or empty response after
    _MAX_ATTEMPTS, matching the contract's failure shape - jm-backend stores the signal with a
    blank summary and moves on rather than blocking on this call."""
    prompt = _context_block(request)
    # Same tenant/agent binding Worker.answer() uses (2 Sep: "same worker, same config, one cost
    # bucket") - without this, generate() calls here are recorded as unattributed spend.
    agent_token = usage.set_agent(AGENT_ID)
    tenant_token = set_tenant(TENANT)
    try:
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                response = provider.generate(prompt, system=SYSTEM, temperature=0.0, prefill="{")
                raw = _parse_llm_json_object(response.text)
                extracted = _ExtractedSummary.model_validate(raw)
            except (json.JSONDecodeError, ValidationError, AttributeError):
                continue
            if not extracted.summary.strip() or not extracted.suggestedNextAction.strip():
                continue
            return SignalSummaryResult(
                summary=extracted.summary.strip(),
                suggestedNextAction=extracted.suggestedNextAction.strip(),
                groundedIn=extracted.groundedIn,
            )
        return None
    finally:
        usage.reset_agent(agent_token)
        reset_tenant(tenant_token)
