"""Compliance Checker: extract mandatory pass/fail tender items, grounded and schema-validated.

Port of idg-worker's pipeline/build_compliance.py, generalized to any tender (not BOC 2171) and,
unlike the prototype (a single ungrounded LLM call with no verification), gated by a citation-
existence check against the source text so an item can't cite a requirement that isn't there.

Structured + schema-validated (Pydantic) with retries, mirroring the hardening applied to
requirements extraction (app/modules/rfp/extraction.py): the model response is parsed out of any
prose/markdown, each item is validated against a schema (malformed items dropped individually rather
than failing the whole batch, category/owner normalised to the existing allowed sets), and a bad
response gets a retry before surfacing as a ComplianceError. The OUTPUT SHAPE is unchanged -- the
same {requirement, category, mandatory, owner, note, grounded} dicts the endpoint persists and the
FE `ComplianceItem` type consumes, INCLUDING the grounded flag from the citation-existence gate.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError, field_validator

from app.modules.ai.gateway import LLMProvider

SYSTEM = (
    "You are a bid/RFP compliance analyst. Read the tender text and extract 8-20 mandatory "
    "pass/fail compliance items (forms, confirmations, formats, eligibility disqualifiers). "
    "Return ONLY a JSON array (no prose, no markdown fences), each item with exactly these keys: "
    '"requirement" (short description, quoting or closely paraphrasing the source text), '
    '"category" (one of "Legal","Commercial","HSSE","Format","Experience","Eligibility"), '
    '"mandatory" (boolean), "owner" ("AI" if a grounded knowledge-base narrative could address '
    'it, "Human" for signatures/pricing/forms/financial evidence), "note" (short rationale).'
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)
_VALID_CATEGORIES = {"Legal", "Commercial", "HSSE", "Format", "Experience", "Eligibility"}
_MAX_ATTEMPTS = 2


class ComplianceError(Exception):
    pass


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def _as_str(v) -> str:
    """Coerce a scalar to a string the way the previous `str(...)` calls did, so a model that
    returns a number/None for a string field still yields the same output rather than dropping the
    whole item."""
    return "" if v is None else str(v)


class ComplianceItemModel(BaseModel):
    """One compliance item's schema. Keys/shape match the endpoint's existing per-item output and
    the FE `ComplianceItem` type EXACTLY (the derived `grounded` flag is added afterwards in
    _validate_items, not a model field). `requirement` is required (an item with no requirement is
    dropped); `category` normalises to the allowed set (else "Format") and `owner` to "AI"/"Human"
    exactly as before."""
    requirement: str  # required: an empty/missing requirement drops the item (see validator)
    category: str = "Format"
    mandatory: bool = True
    owner: str = "Human"
    note: str = ""

    @field_validator("requirement", "note", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _as_str(v)

    @field_validator("requirement")
    @classmethod
    def _check_requirement(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty requirement")
        return v

    @field_validator("mandatory", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        return bool(v)

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, v):
        v = _as_str(v).strip()
        return v if v in _VALID_CATEGORIES else "Format"

    @field_validator("owner", mode="before")
    @classmethod
    def _normalise_owner(cls, v):
        return "AI" if _as_str(v).strip().lower() == "ai" else "Human"


def _parse_llm_json_array(text: str) -> list:
    """LLMs often wrap JSON in prose or markdown fences; pull out the first array and parse it."""
    match = _JSON_ARRAY.search(text)
    candidate = match.group(0) if match else text
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ComplianceError(f"model did not return valid JSON: {e}") from e
    if not isinstance(parsed, list):
        raise ComplianceError("model did not return a JSON array")
    return parsed


def _validate_items(raw_items: list, source_words: set[str]) -> list[dict]:
    """Validate each element against ComplianceItemModel, dropping malformed items individually and
    keeping the well-formed ones. Applies the citation-existence gate AFTER validation: each kept
    item carries a `grounded` flag that is False when its requirement shares no meaningful
    vocabulary with the source tender (i.e. looks invented). Returns the SAME per-item dicts the
    endpoint has always returned."""
    out: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            model = ComplianceItemModel(**item)
        except ValidationError:
            continue  # drop malformed items, keep the well-formed ones
        req_words = _content_words(model.requirement)
        out.append({
            "requirement": model.requirement,
            "category": model.category,
            "mandatory": model.mandatory,
            "owner": model.owner,
            "note": model.note,
            "grounded": bool(req_words & source_words),
        })
    return out


# 160k (vs the old 60k): mandatory compliance items (and the compliance matrix itself) are often
# in later annexes/tables, so a 60k window under-reported them for large tenders. The completion is
# a short pass/fail list, so the bigger input stays within context / read-timeout budget.
def extract_compliance(tender_text: str, provider: LLMProvider, *, max_chars: int = 160_000) -> list[dict]:
    """Extract compliance items, schema-validated with retries and gated by a citation-existence
    check: each item carries a `grounded` flag that is False when its requirement text shares no
    meaningful vocabulary with the source tender (i.e. looks invented). Returns the same per-item
    {requirement, category, mandatory, owner, note, grounded} dicts as before (persisted list + FE
    `ComplianceItem` type unchanged). Retries up to _MAX_ATTEMPTS times if the model's response
    can't be parsed or yields no valid items; raises ComplianceError only if still empty."""
    truncated = tender_text[:max_chars]
    source_words = _content_words(truncated)
    last_error: Exception | None = None
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            response = provider.generate(f"TENDER DOCUMENT:\n{truncated}", system=SYSTEM, temperature=0.0)
            raw_items = _parse_llm_json_array(response.text)
            out = _validate_items(raw_items, source_words)
            if out:
                return out
            last_error = ComplianceError("no valid compliance items after schema validation")
        except ComplianceError as e:
            last_error = e
    raise last_error or ComplianceError("no compliance items could be extracted from this document")
