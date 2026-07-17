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

# A whole typical tender fits in one model call (Claude handles ~200k ctx); idg's own generalized
# extractor (app/agents/requirements_extractor.py) uses exactly this budget with a single call.
MAX_CONTEXT_CHARS = 160_000
# idg caps its requirements catalogue at 20 items ("Include at most 20 items."); we mirror that so
# a tender yields a small, COARSE set of top-level sections (~10-20) rather than a long flat list.
MAX_ITEMS = 20

SYSTEM = (
    "You are a bid-management analyst. Read the tender documents (terms of reference, evaluation "
    "grid, instructions to tenderers) and produce a requirements CATALOGUE: the coarse list of "
    "the top-level sections or appendices the bidder must respond to. Each item is a whole "
    "section a tenderer responds to, NOT a single sentence or sub-clause.\n\n"
    "For EACH section, classify it as exactly one of:\n"
    "- KB: a narrative/technical section that can be drafted from the bidder's knowledge base "
    "(methodology, approach, experience, organisation, quality, HSSE, etc.).\n"
    "- DATA: requires specific records only the bidder holds (CVs, equipment lists, financial "
    "statements) -- not AI-answerable.\n"
    "- MANUAL: a prescribed commercial/legal form or pricing schedule completed by humans.\n"
    "- COMPLIANCE: a signed confirmation or declaration of eligibility.\n\n"
    "Return ONLY a JSON array (no prose, no markdown fences). Each element has exactly these keys: "
    '"id" (a short top-level section id from the document\'s own numbering if present, e.g. '
    '"A1", "B3"; sequential if the document has none -- one id per top-level section), "title" '
    '(the section\'s short title), "classification" (one of "KB", "DATA", "MANUAL", '
    '"COMPLIANCE"), and "requirement" (a 1-3 sentence description of what the bidder must '
    "provide for that section). "
    "When a section clearly breaks down into distinct numbered (e.g. B1.1, B1.2) or lettered "
    "((a), (b)) sub-requirements in the source, list those sub-parts on their OWN LINES inside "
    "the requirement text (one per line, keeping the source's own numbering) so each can be "
    "answered separately -- do NOT emit them as separate top-level items. "
    "Include AT MOST 20 items: aim for a small, COARSE set of top-level sections (roughly 10-20 "
    "for a whole tender, following the document's own top-level lettered/numbered headings, e.g. "
    "commercial A1..A4 and technical B1..Bn). Do not invent items that are not in the documents."
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)
_VALID_CLASSIFICATIONS = {"KB", "DATA", "MANUAL", "COMPLIANCE"}
_MAX_ATTEMPTS = 2
# A dotted sub-section heading inside a requirement's text ("B1.1", "A2.3"). Generalised from
# idg's BOC-specific `B\d+\.\d+` so it fires for any lettered top-level section V2 extracts.
_SUBSECTION_HEADING = re.compile(r"^\s*[A-Za-z]{1,3}\d+\.\d+")


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


def extract_requirements(tender_text: str, provider: LLMProvider, *, max_chars: int = MAX_CONTEXT_CHARS,
                         id_prefix: str = "") -> list[dict]:
    """Extract a document-agnostic, COARSE requirements catalogue from raw tender text.

    Returns a list of {id, title, classification, requirement} dicts, schema-validated (malformed
    items dropped individually) and capped at MAX_ITEMS (idg's "at most 20 items") so a tender
    yields a small set of coarse top-level sections rather than a long flat list. Retries once if
    the model's response can't be parsed at all.

    A whole typical tender fits in one call (max_chars defaults to MAX_CONTEXT_CHARS = 160k, like
    idg's requirements_extractor); the smaller per-chunk budget is only used on the >160k fallback
    path (see generation.extract_requirements_chunked).

    `id_prefix` disambiguates the fallback id ("R1", "R2", ...) used when the model omits one --
    only relevant when this is called once per chunk of a larger document so two chunks' fallback
    ids can't collide.
    """
    truncated = tender_text[:max_chars]
    last_error: Exception | None = None
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            response = provider.generate(f"TENDER DOCUMENT:\n{truncated}", system=SYSTEM, temperature=0.0)
            raw_items = _parse_llm_json_array(response.text)
            out = _validate_items(raw_items, id_prefix=id_prefix)
            if out:
                return out[:MAX_ITEMS]
            last_error = ExtractionError("no valid requirements after schema validation")
        except ExtractionError as e:
            last_error = e
    raise last_error or ExtractionError("no requirements could be extracted from this document")


def split_subsections(req_id: str, requirement: str) -> list[dict]:
    """Derive a requirement's sub-sections from its OWN text (port of idg-worker's
    app/agents/answer.py::split_subsections). Prefers dotted numbered headings ("B1.1", "B1.2");
    falls back to top-level (a)/(b) clauses; otherwise a single sub-section. Each sub-section is
    independently gradeable, so a coarse extracted section can expand into per-sub-part answers
    without the extractor having to emit one item per sub-requirement.

    Returns a list of {"sub_id", "title", "body"}; a single-element list means "no split" (the
    requirement is answered directly on its section).
    """
    lines = [line.rstrip() for line in (requirement or "").split("\n") if line.strip()]
    subs: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if _SUBSECTION_HEADING.match(line):
            if cur:
                subs.append(cur)
            cur = {"title": line.strip(), "body": []}
        elif cur is not None:
            cur["body"].append(line.strip())
    if cur:
        subs.append(cur)
    if len(subs) >= 2:
        # body = the heading line plus any following detail, so the question is self-contained
        return [{"sub_id": s["title"].split()[0], "title": s["title"],
                 "body": "\n".join([s["title"], *s["body"]]).strip()} for s in subs]
    parts = re.split(r"(?m)(?=^\s*\([a-z]\)\s)", requirement or "")
    parts = [p.strip() for p in parts if re.match(r"^\([a-z]\)", p.strip() or "")]
    if len(parts) >= 2:
        return [{"sub_id": re.match(r"^\(([a-z])\)", p).group(0), "title": p.split("\n")[0][:70],
                 "body": p} for p in parts]
    return [{"sub_id": req_id, "title": req_id, "body": requirement or ""}]


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
