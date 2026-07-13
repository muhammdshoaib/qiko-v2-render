"""Document-agnostic requirement extraction.

Replaces the IDG prototype's hand-curated, tender-specific CATALOGUE (pipeline/build_requirements_map.py
in the original idg-worker) with a single LLM pass that works for any uploaded tender document.

Schema-validated (Pydantic) with a one-shot retry on failure, matching the hardening applied to
idg-worker's own generalized extractor (app/agents/requirements_extractor.py) after it went live
against a second, real, non-BOC-2171 tender (PROC/ECS/2025/028) -- malformed items are dropped
individually rather than failing the whole batch, and a bad model response gets one retry before
surfacing as an error.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError, field_validator

from app.modules.ai.gateway import LLMProvider

SYSTEM = (
    "You are a bid/RFP analyst. Read the tender document text and extract every discrete "
    "requirement or section a bidder must respond to. Return ONLY a JSON array (no prose, no "
    "markdown fences), where each item has exactly these keys: "
    '"id" (a section id inferred from the document\'s own numbering if present, otherwise '
    'sequential -- use a short top-level id like "A1" or "B3" for a section with no distinct '
    'numbered sub-parts, but if the section itself contains multiple clearly distinct numbered '
    'or lettered sub-requirements (e.g. the source text reads "B1.1 Contractor\'s Organogram" '
    'and "B1.2 Contractor\'s Organisation" under a "B1" heading), emit ONE ITEM PER SUB-PART with '
    'a dotted id ("B1.1", "B1.2", ...) instead of one item for the whole section -- each becomes '
    "its own independently gradeable answer, which is what a human reviewer actually needs; do "
    'not invent sub-parts that are not clearly present in the source), "title" (for a dotted id, '
    'prefix the sub-part\'s own title with the parent heading\'s title and " \u2014 ", e.g. '
    '"Organisational Structure & Manpower \u2014 Contractor\'s Organogram" for id "B1.1" under '
    'heading "B1 Organisational Structure & Manpower"; for a non-dotted id, just the section '
    'title), "classification" (one of "KB", "DATA", "MANUAL", "COMPLIANCE" -- KB = a narrative '
    "answer can be grounded in a knowledge base; DATA = requires the bidder's own factual data "
    "(CVs, pricing, equipment lists); MANUAL = a prescribed form/template completed outside the "
    'AI; COMPLIANCE = a pass/fail confirmation or signature), and "requirement" (the verbatim or '
    "closely-paraphrased requirement text for that item)."
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)
_VALID_CLASSIFICATIONS = {"KB", "DATA", "MANUAL", "COMPLIANCE"}
_MAX_ATTEMPTS = 2


class ExtractionError(Exception):
    pass


class _ExtractedItem(BaseModel):
    id: str = ""
    title: str = ""
    classification: str = "KB"
    requirement: str

    @field_validator("classification")
    @classmethod
    def _check_classification(cls, v: str) -> str:
        v = (v or "").strip().upper()
        return v if v in _VALID_CLASSIFICATIONS else "KB"

    @field_validator("requirement")
    @classmethod
    def _check_requirement(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty requirement")
        return v


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


def _validate_items(raw_items: list, *, id_prefix: str = "") -> list[dict]:
    out: list[dict] = []
    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        try:
            validated = _ExtractedItem(**item)
        except ValidationError:
            continue  # drop malformed items, keep the well-formed ones
        out.append({
            "id": validated.id or f"{id_prefix}R{i + 1}",
            "title": validated.title or f"Section {i + 1}",
            "classification": validated.classification,
            "requirement": validated.requirement,
        })
    return out


def extract_requirements(tender_text: str, provider: LLMProvider, *, max_chars: int = 60_000,
                         id_prefix: str = "") -> list[dict]:
    """Extract a document-agnostic requirements list from raw tender text.

    Returns a list of {id, title, classification, requirement} dicts, schema-validated (malformed
    items dropped individually). Retries once if the model's response can't be parsed at all.

    `id_prefix` disambiguates the fallback id ("R1", "R2", ...) used when the model omits one --
    only relevant when this is called once per chunk of a larger document (see chunk_document /
    extract_requirements_from_document) so two chunks' fallback ids can't collide.
    """
    truncated = tender_text[:max_chars]
    last_error: Exception | None = None
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            response = provider.generate(f"TENDER DOCUMENT:\n{truncated}", system=SYSTEM, temperature=0.0)
            raw_items = _parse_llm_json_array(response.text)
            out = _validate_items(raw_items, id_prefix=id_prefix)
            if out:
                return out
            last_error = ExtractionError("no valid requirements after schema validation")
        except ExtractionError as e:
            last_error = e
    raise last_error or ExtractionError("no requirements could be extracted from this document")


def chunk_document(text: str, *, max_chars: int = 25_000, overlap_chars: int = 1_500) -> list[str]:
    """Split a long tender document into overlapping chunks so extraction no longer needs one LLM
    call to cover the entire document in a single completion. A tender in the tens of thousands
    of chars was routinely hitting Bedrock's read timeout in one shot -- both the prompt (a whole
    document) and the expected completion (every requirement, sub-split where applicable) got too
    large to finish reliably within any reasonable timeout. Splitting into smaller, independent
    chunks that extract in parallel (see rfp/router.py) fixes both: each call is faster and the
    document is no longer truncated at a fixed char budget regardless of its real length.

    Splits on a paragraph boundary within the tail of the window where possible, so a requirement
    's text isn't cut mid-sentence; a bit of overlap between consecutive chunks means a section
    straddling a boundary is still fully visible in at least one chunk (extract_requirements_from_
    document dedupes by id, so seeing the same section twice is harmless)."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            search_from = start + int(max_chars * 0.8)
            boundary = text.rfind("\n\n", search_from, end)
            if boundary == -1:
                boundary = text.rfind("\n", search_from, end)
            if boundary != -1 and boundary > start:
                end = boundary
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(end - overlap_chars, 0)
    return chunks
