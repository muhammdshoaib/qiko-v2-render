"""Document-agnostic requirement extraction.

Replaces the IDG prototype's hand-curated, tender-specific CATALOGUE (pipeline/build_requirements_map.py
in the original idg-worker) with a single LLM pass that works for any uploaded tender document.
"""
from __future__ import annotations

import json
import re

from app.modules.ai.gateway import LLMProvider

SYSTEM = (
    "You are a bid/RFP analyst. Read the tender document text and extract every discrete "
    "requirement or section a bidder must respond to. Return ONLY a JSON array (no prose, no "
    "markdown fences), where each item has exactly these keys: "
    '"id" (short section id like "A1" or "B3", inferred from the document\'s own numbering if '
    'present, otherwise sequential), "title" (short section title), '
    '"classification" (one of "KB", "DATA", "MANUAL", "COMPLIANCE" -- KB = a narrative answer '
    "can be grounded in a knowledge base; DATA = requires the bidder's own factual data (CVs, "
    "pricing, equipment lists); MANUAL = a prescribed form/template completed outside the AI; "
    'COMPLIANCE = a pass/fail confirmation or signature), and "requirement" (the verbatim or '
    "closely-paraphrased requirement text)."
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)
_VALID_CLASSIFICATIONS = {"KB", "DATA", "MANUAL", "COMPLIANCE"}


class ExtractionError(Exception):
    pass


def _parse_llm_json_array(text: str) -> list[dict]:
    """LLMs often wrap JSON in prose or markdown fences; pull out the first array and parse it."""
    match = _JSON_ARRAY.search(text)
    candidate = match.group(0) if match else text
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"model did not return valid JSON: {e}") from e
    if not isinstance(parsed, list):
        raise ExtractionError("model did not return a JSON array")
    return parsed


def extract_requirements(tender_text: str, provider: LLMProvider, *, max_chars: int = 60_000) -> list[dict]:
    """Extract a document-agnostic requirements list from raw tender text.

    Returns a list of {id, title, classification, requirement} dicts, validated and normalised
    (unknown/missing classification defaults to "KB" so nothing silently drops out of the pipeline).
    """
    truncated = tender_text[:max_chars]
    response = provider.generate(f"TENDER DOCUMENT:\n{truncated}", system=SYSTEM, temperature=0.0)
    items = _parse_llm_json_array(response.text)

    out: list[dict] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not item.get("requirement"):
            continue
        classification = str(item.get("classification", "KB")).upper()
        if classification not in _VALID_CLASSIFICATIONS:
            classification = "KB"
        out.append({
            "id": str(item.get("id") or f"R{i + 1}"),
            "title": str(item.get("title") or f"Section {i + 1}"),
            "classification": classification,
            "requirement": str(item["requirement"]),
        })
    if not out:
        raise ExtractionError("no requirements could be extracted from this document")
    return out
