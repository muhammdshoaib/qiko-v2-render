"""Extract a LeadQualification (qualification.py) from a WhatsApp conversation so far.

Structured LLM pass, same pattern as rfp/extraction.py: a JSON-only system prompt, Pydantic
validation, and a bounded retry on a malformed response. Unlike rfp/extraction.py this never
raises up to the caller on failure: a lead mid-qualification always needs SOME routing decision,
so an unparseable response falls back to LeadQualification() (everything unknown), which
route_outcome() already sends to "webinar" rather than wrongly promising a meeting or wrongly
escalating.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from app.modules.ai.gateway import LLMProvider
from app.modules.joseph_mews.qualification import FundingMethod, LeadQualification, Timeline

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_MAX_ATTEMPTS = 2

SYSTEM = (
    "You read a WhatsApp conversation between Joe, a property-investment assistant, and a lead. "
    "Extract ONLY qualification signals the lead has actually stated; never infer or guess a "
    "value that was not said.\n\n"
    "Return ONLY a JSON object (no prose, no markdown fences) with exactly these keys:\n"
    '"timeline": one of "soon" (wants to move in the next few months / ASAP), "future" '
    '(planning/researching, next year or later), "unknown" (not stated).\n'
    '"has_budget_signal": true if the lead mentioned any budget number, range, or "cash ready", '
    "else false.\n"
    '"funding_method": one of "cash", "mortgage", "unknown".\n'
    '"journey_stage": a short free-text label such as "first_time" or "experienced" if stated, '
    'else "".\n'
    '"interest_signal": true if the lead asked a specific/technical question or named a location '
    "or property, else false.\n"
    '"wants_human": true if the lead explicitly asked to speak to a person, said they already '
    "spoke to someone at the company, or raised an objection, else false.\n"
    '"other_factors": a small integer count (0-3) of any other positive buying signals not '
    "captured above."
)


class _ExtractedQualification(BaseModel):
    timeline: str = "unknown"
    has_budget_signal: bool = False
    funding_method: str = "unknown"
    journey_stage: str = ""
    interest_signal: bool = False
    wants_human: bool = False
    other_factors: int = 0


def _parse_llm_json_object(text: str) -> dict:
    match = _JSON_OBJECT.search(text)
    return json.loads(match.group(0) if match else text)


def _safe_enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _to_qualification(extracted: _ExtractedQualification) -> LeadQualification:
    return LeadQualification(
        timeline=_safe_enum(Timeline, extracted.timeline, Timeline.unknown),
        has_budget_signal=extracted.has_budget_signal,
        funding_method=_safe_enum(FundingMethod, extracted.funding_method, FundingMethod.unknown),
        journey_stage=extracted.journey_stage,
        interest_signal=extracted.interest_signal,
        wants_human=extracted.wants_human,
        other_factors=max(0, min(extracted.other_factors, 3)),
    )


def extract_qualification(conversation_text: str, provider: LLMProvider) -> LeadQualification:
    """Best-effort extraction. Never raises: any failure after _MAX_ATTEMPTS falls back to an
    all-unknown LeadQualification, which route_outcome() treats as low-signal (webinar), not a
    false positive in either direction (never a wrongly-confident meeting or escalation)."""
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            response = provider.generate(conversation_text, system=SYSTEM, temperature=0.0, prefill="{")
            raw = _parse_llm_json_object(response.text)
            extracted = _ExtractedQualification.model_validate(raw)
            return _to_qualification(extracted)
        except (json.JSONDecodeError, ValidationError, AttributeError):
            continue
    return LeadQualification()
