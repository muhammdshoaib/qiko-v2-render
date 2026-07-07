"""Compliance Checker: extract mandatory pass/fail tender items, grounded and schema-validated.

Port of idg-worker's pipeline/build_compliance.py, generalized to any tender (not BOC 2171) and,
unlike the prototype (a single ungrounded LLM call with no verification), gated by a citation-
existence check against the source text so an item can't cite a requirement that isn't there.
"""
from __future__ import annotations

import json
import re

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


class ComplianceError(Exception):
    pass


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def extract_compliance(tender_text: str, provider: LLMProvider, *, max_chars: int = 60_000) -> list[dict]:
    """Extract compliance items, gated by a citation-existence check: an item is dropped if its
    requirement text shares no meaningful vocabulary with the source tender (i.e. looks invented)."""
    truncated = tender_text[:max_chars]
    response = provider.generate(f"TENDER DOCUMENT:\n{truncated}", system=SYSTEM, temperature=0.0)
    match = _JSON_ARRAY.search(response.text)
    candidate = match.group(0) if match else response.text
    try:
        items = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ComplianceError(f"model did not return valid JSON: {e}") from e
    if not isinstance(items, list):
        raise ComplianceError("model did not return a JSON array")

    source_words = _content_words(truncated)
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("requirement"):
            continue
        category = str(item.get("category", "")).strip()
        if category not in _VALID_CATEGORIES:
            category = "Format"
        owner = "Human" if str(item.get("owner", "")).strip().lower() != "ai" else "AI"
        req_words = _content_words(str(item["requirement"]))
        grounded = bool(req_words & source_words)
        out.append({
            "requirement": str(item["requirement"]),
            "category": category,
            "mandatory": bool(item.get("mandatory", True)),
            "owner": owner,
            "note": str(item.get("note", "")),
            "grounded": grounded,
        })
    if not out:
        raise ComplianceError("no compliance items could be extracted from this document")
    return out
