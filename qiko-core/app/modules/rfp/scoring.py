"""Opportunity scoring: qualify a tender against a worker's own criteria before committing to a
full bid response. Generic and reusable -- criteria are configured per agent (Agent.config's
"opportunity_criteria" list, same free-form config Vapi/Calendly/Salesforce settings live in),
not hardcoded to any one client's rules. This is a different question from the answer-drafting
pipeline (Pre Sales Writer Worker): that one answers "what do we say for section B3", this one
answers "should we even bid this one".
"""
from __future__ import annotations

import json
import re

from app.modules.ai.gateway import LLMProvider

SYSTEM = (
    "You are a bid/sales qualification analyst. Read the tender/opportunity text and score it "
    "against the criteria the client has provided. Return ONLY a JSON object (no prose, no "
    'markdown fences) with exactly these keys: "score" (an integer 0-100, how well this '
    'opportunity fits the criteria overall), "qualified" (boolean, true if this is worth '
    'pursuing), "rationale" (2-3 sentences explaining the score), and "criteria_results" (a '
    'JSON array with one item per criterion given, in the same order, each an object with '
    '"criterion" (the criterion text, verbatim), "met" (boolean), and "note" (a short reason, '
    "grounded in the tender text -- never invent facts not present in the document)."
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_DEFAULT_CRITERIA = ("Is the opportunity's scope a reasonable match for our services?",
                     "Are the deadlines/timeline realistic to respond to?",
                     "Is there anything in the document that would disqualify us outright?")


class ScoringError(Exception):
    pass


def score_opportunity(tender_text: str, criteria: list[str], provider: LLMProvider,
                      *, max_chars: int = 60_000) -> dict:
    """Score a tender/opportunity against a list of criteria. Falls back to a small set of
    generic criteria if the worker hasn't configured any yet, so this is never a dead end."""
    active_criteria = [c for c in (criteria or []) if c.strip()] or list(_DEFAULT_CRITERIA)
    truncated = tender_text[:max_chars]
    prompt = ("CRITERIA:\n" + "\n".join(f"- {c}" for c in active_criteria) +
             f"\n\nOPPORTUNITY/TENDER TEXT:\n{truncated}")
    response = provider.generate(prompt, system=SYSTEM, temperature=0.0)
    match = _JSON_OBJECT.search(response.text)
    candidate = match.group(0) if match else response.text
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ScoringError(f"model did not return valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ScoringError("model did not return a JSON object")

    try:
        score = max(0, min(100, int(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    criteria_results = []
    for item in data.get("criteria_results") or []:
        if not isinstance(item, dict):
            continue
        criteria_results.append({
            "criterion": str(item.get("criterion", "")), "met": bool(item.get("met")),
            "note": str(item.get("note", "")),
        })
    rationale = str(data.get("rationale", "")).strip()
    if not rationale:
        raise ScoringError("model did not return a usable rationale")

    return {
        "score": score, "qualified": bool(data.get("qualified")), "rationale": rationale,
        "criteria_results": criteria_results or [{"criterion": c, "met": False, "note": ""} for c in active_criteria],
    }
