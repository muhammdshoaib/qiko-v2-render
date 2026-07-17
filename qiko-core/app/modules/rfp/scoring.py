"""Opportunity scoring: qualify a tender against a worker's own criteria before committing to a
full bid response. Generic and reusable -- criteria are configured per agent (Agent.config's
"opportunity_criteria" list, same free-form config Vapi/Calendly/Salesforce settings live in),
not hardcoded to any one client's rules. This is a different question from the answer-drafting
pipeline (Pre Sales Writer Worker): that one answers "what do we say for section B3", this one
answers "should we even bid this one".

Uses the same robustness harness as the requirements/brief/compliance extractions: a Pydantic
schema + per-item validation (malformed criteria dropped, valid kept) + fenced-JSON parsing +
retries, so scoring is consistent and predictable rather than failing on the first bad response.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError, field_validator

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
_MAX_ATTEMPTS = 2
_DEFAULT_CRITERIA = ("Is the opportunity's scope a reasonable match for our services?",
                     "Are the deadlines/timeline realistic to respond to?",
                     "Is there anything in the document that would disqualify us outright?")


class ScoringError(Exception):
    pass


class _CriterionResult(BaseModel):
    criterion: str = ""
    met: bool = False
    note: str = ""

    @field_validator("criterion", "note", mode="before")
    @classmethod
    def _as_str(cls, v: object) -> str:
        return str(v if v is not None else "").strip()


class _Scoring(BaseModel):
    score: int = 0
    qualified: bool = False
    rationale: str
    # Raw list so one malformed criterion is dropped individually (validated per-element below)
    # rather than sinking the whole score.
    criteria_results: list = []

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v: object) -> int:
        try:
            return max(0, min(100, int(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    @field_validator("rationale", mode="before")
    @classmethod
    def _require_rationale(cls, v: object) -> str:
        s = str(v if v is not None else "").strip()
        if not s:
            raise ValueError("empty rationale")
        return s


def _parse_json_object(raw: str) -> dict:
    body = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    m = _JSON_OBJECT.search(body)
    if not m:
        raise ValueError("no JSON object found in model output")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    return data


def score_opportunity(tender_text: str, criteria: list[str], provider: LLMProvider,
                      *, max_chars: int = 160_000) -> dict:
    """Score a tender/opportunity against a list of criteria. Falls back to a small set of
    generic criteria if the worker hasn't configured any yet, so this is never a dead end.
    Validates the model output against a schema and retries before giving up."""
    active_criteria = [c for c in (criteria or []) if c.strip()] or list(_DEFAULT_CRITERIA)
    truncated = tender_text[:max_chars]
    prompt = ("CRITERIA:\n" + "\n".join(f"- {c}" for c in active_criteria) +
             f"\n\nOPPORTUNITY/TENDER TEXT:\n{truncated}")

    last_error = "unknown error"
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            response = provider.generate(prompt, system=SYSTEM, temperature=0.0)
            data = _parse_json_object(response.text)
            model = _Scoring(**data)
            results = []
            for item in model.criteria_results:
                if not isinstance(item, dict):
                    continue
                try:
                    cr = _CriterionResult(**item)
                except ValidationError:
                    continue  # drop a malformed criterion, keep the rest
                results.append({"criterion": cr.criterion, "met": cr.met, "note": cr.note})
            return {
                "score": model.score, "qualified": model.qualified, "rationale": model.rationale,
                "criteria_results": results or [{"criterion": c, "met": False, "note": ""} for c in active_criteria],
            }
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_error = str(e)
            continue
    raise ScoringError(f"could not score opportunity after {_MAX_ATTEMPTS} attempts: {last_error}")
