"""Tender Brief: summarise scope/rules/format/dates and flag likely gaps, grounded in the tender.

Port of idg-worker's pipeline/build_brief.py, generalized to any tender document.
"""
from __future__ import annotations

import json
import re

from app.modules.ai.gateway import LLMProvider

SYSTEM = (
    "You are a bid manager. Read the tender text and produce a structured brief. Return ONLY a "
    "JSON object (no prose, no markdown fences) with exactly these keys: "
    '"summary" (3-4 sentences), "scope" (string), "submission_format" (string), '
    '"key_dates" (array of strings), "success_criteria" (array of strings), '
    '"gaps_and_risks" (array of strings).'
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_REQUIRED_KEYS = ("summary", "scope", "submission_format", "key_dates", "success_criteria", "gaps_and_risks")


class BriefError(Exception):
    pass


# 160k (vs the old 60k): the brief's key dates + success criteria + gaps frequently live deep in
# the pack (annex templates, later schedules, tables now that docx tables are extracted), so a
# 60k window silently dropped them for large tenders. Output stays a small JSON object, so the
# larger input is well within the model's context / read timeout.
def extract_brief(tender_text: str, provider: LLMProvider, *, max_chars: int = 160_000) -> dict:
    truncated = tender_text[:max_chars]
    response = provider.generate(f"TENDER DOCUMENT:\n{truncated}", system=SYSTEM, temperature=0.0)
    match = _JSON_OBJECT.search(response.text)
    candidate = match.group(0) if match else response.text
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise BriefError(f"model did not return valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise BriefError("model did not return a JSON object")

    brief = {
        "summary": str(data.get("summary", "")),
        "scope": str(data.get("scope", "")),
        "submission_format": str(data.get("submission_format", "")),
        "key_dates": [str(x) for x in data.get("key_dates", []) if x],
        "success_criteria": [str(x) for x in data.get("success_criteria", []) if x],
        "gaps_and_risks": [str(x) for x in data.get("gaps_and_risks", []) if x],
    }
    if not brief["summary"]:
        raise BriefError("model did not return a usable summary")
    return brief
