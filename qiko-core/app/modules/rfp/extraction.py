"""Document-agnostic requirement extraction.

Replaces the IDG prototype's hand-curated, tender-specific CATALOGUE (pipeline/build_requirements_map.py
in the original idg-worker) with a single LLM pass that works for any uploaded tender document.

Structured + schema-validated (Pydantic) with retries on failure, matching the hardening applied to
idg-worker's own generalized extractor (app/agents/requirements_extractor.py) after it went live
against a second, real, non-BOC-2171 tender (PROC/ECS/2025/028) -- malformed entries are dropped
individually rather than failing the whole batch, and a bad model response gets a retry before
surfacing as an error.

Sub-sections are an EXPLICIT, model-returned `subsections` array on each top-level section rather
than something regex-derived from the requirement prose (see split_subsections, kept only as a
legacy fallback). That makes the section+sub-section tree deterministic on every tender instead of
depending on whether the model happened to embed "B1.1"/"(a)" markers in free text.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.modules.ai.gateway import LLMProvider

# A whole typical tender fits in one model call (Claude handles ~200k ctx); idg's own generalized
# extractor (app/agents/requirements_extractor.py) uses exactly this budget with a single call.
MAX_CONTEXT_CHARS = 160_000
# idg caps its requirements catalogue at 20 items ("Include at most 20 items."); we mirror that so
# a tender yields a small, COARSE set of top-level sections (~10-20) rather than a long flat list.
MAX_ITEMS = 20
# Sub-sections were previously unbounded, so a single over-eager section could mint hundreds of
# sub-requirements -- each one a draft LLM call, exploding cost and the drafts stage. Cap them like
# the top-level list so a section stays a small, coarse set of sub-parts.
MAX_SUBS = 15

SYSTEM = (
    "You are a bid-management analyst. Read the tender documents (terms of reference, evaluation "
    "grid, instructions to tenderers) and produce a requirements CATALOGUE: the coarse list of "
    "the top-level sections or appendices the bidder must respond to. Each item is a whole "
    "section a tenderer responds to, NOT a single sentence or sub-clause.\n\n"
    "For EACH section (and each sub-section), classify it as exactly one of:\n"
    "- KB: a narrative/technical section that can be drafted from the bidder's knowledge base "
    "(methodology, approach, experience, organisation, quality, HSSE, etc.).\n"
    "- DATA: requires specific records only the bidder holds (CVs, equipment lists, financial "
    "statements) -- not AI-answerable.\n"
    "- MANUAL: a prescribed commercial/legal form or pricing schedule completed by humans.\n"
    "- COMPLIANCE: a signed confirmation or declaration of eligibility.\n\n"
    "Return ONLY a JSON array (no prose, no markdown fences) of AT MOST 20 top-level sections. "
    "Each element has exactly these keys: "
    '"id" (a short top-level section id from the document\'s own numbering if present, e.g. '
    '"A1", "B3"; sequential if the document has none -- one id per top-level section), "title" '
    '(the section\'s short title), "classification" (one of "KB", "DATA", "MANUAL", '
    '"COMPLIANCE"), "requirement" (a 1-3 sentence description of what the bidder must provide for '
    'that section), and "subsections" (a JSON array). '
    "For EACH section, list its discrete sub-requirements in the \"subsections\" array: each entry "
    "is a distinct thing the tenderer answers or provides SEPARATELY, with keys \"title\" (its "
    'short title), "classification" (one of the four above), and "requirement" (a 1-3 sentence '
    "description of that sub-part). If a section has no natural sub-parts, its \"subsections\" is "
    "[]. Do NOT emit sub-parts as separate top-level items -- nest them under their section. "
    "Include AT MOST 20 top-level sections: aim for a small, COARSE set (roughly 10-20 for a "
    "whole tender, following the document's own top-level lettered/numbered headings, e.g. "
    "commercial A1..A4 and technical B1..Bn). Do not invent sections or sub-sections that are not "
    "in the documents."
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)
_VALID_CLASSIFICATIONS = {"KB", "DATA", "MANUAL", "COMPLIANCE"}
_MAX_ATTEMPTS = 2
# A dotted sub-section heading inside a requirement's text ("B1.1", "A2.3"). Generalised from
# idg's BOC-specific `B\d+\.\d+` so it fires for any lettered top-level section V2 extracts.
# Only used by split_subsections, the LEGACY fallback for flat backfills.
_SUBSECTION_HEADING = re.compile(r"^\s*[A-Za-z]{1,3}\d+\.\d+")


class ExtractionError(Exception):
    pass


def _normalise_classification(v: str) -> str:
    v = (v or "").strip().upper()
    return v if v in _VALID_CLASSIFICATIONS else "KB"


class ExtractedSubsection(BaseModel):
    """A discrete sub-requirement the tenderer answers/provides separately, returned EXPLICITLY by
    the model as an element of a section's `subsections` array (no regex over prose)."""
    title: str  # required: a missing/empty title drops the sub-section (see validator)
    classification: str = "KB"
    requirement: str = ""

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty title")
        return v

    @field_validator("classification")
    @classmethod
    def _check_classification(cls, v: str) -> str:
        return _normalise_classification(v)

    @field_validator("requirement")
    @classmethod
    def _check_requirement(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty requirement")
        return v


class ExtractedSection(BaseModel):
    """A top-level section the tenderer responds to, with its sub-requirements as an EXPLICIT
    nested `subsections` array. `requirement` may be empty when the section is purely a container
    for its sub-sections; such a section is still kept as long as it has at least one valid
    sub-section (see _validate_sections)."""
    id: str = ""
    title: str  # required: a missing/empty title drops the section (see validator)
    classification: str = "KB"
    requirement: str = ""
    # Kept as raw dicts (not typed ExtractedSubsection) so ONE malformed sub-section is dropped
    # individually rather than sinking the whole section.
    subsections: list = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty title")
        return v

    @field_validator("classification")
    @classmethod
    def _check_classification(cls, v: str) -> str:
        return _normalise_classification(v)

    @field_validator("requirement")
    @classmethod
    def _check_requirement(cls, v: str) -> str:
        return (v or "").strip()


def _parse_llm_json_array(text: str, *, truncated: bool = False) -> list[dict]:
    """LLMs often wrap JSON in prose or markdown fences; pull out the first array and parse it.

    `truncated` says the provider stopped at its output ceiling, so the text is a prefix and the
    parse was never going to succeed. Saying that plainly matters: the previous message blamed the
    model's JSON for a limit we set, which sent people looking for a prompt or model problem
    (QIKO-1081)."""
    match = _JSON_ARRAY.search(text)
    candidate = match.group(0) if match else text
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        if truncated:
            raise ExtractionError(
                "the model hit its output-token ceiling and the response was cut off mid-document; "
                "raise max_tokens for this call rather than retrying") from e
        raise ExtractionError(f"model did not return valid JSON: {e}") from e
    if not isinstance(parsed, list):
        raise ExtractionError("model did not return a JSON array")
    return parsed


def _validate_sections(raw_items: list, *, id_prefix: str = "") -> list[dict]:
    """Validate each top-level element against ExtractedSection, dropping malformed sections (and,
    within a kept section, malformed sub-sections) individually. Assigns hierarchical codes
    deterministically: a top-level code per section (the model's own id, else "{id_prefix}R{n}")
    and sub-section codes as "{parentCode}.{n}" -- so tree._top_level_code still groups a
    sub-section under its parent and the rollups keep working. A section with neither a requirement
    of its own NOR any valid sub-section has nothing answerable and is dropped."""
    out: list[dict] = []
    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        try:
            section = ExtractedSection(**item)
        except ValidationError:
            continue  # drop malformed sections, keep the well-formed ones
        code = section.id or f"{id_prefix}R{i + 1}"
        subs: list[dict] = []
        for raw_sub in section.subsections:
            if len(subs) >= MAX_SUBS:
                break  # cap sub-sections per section (see MAX_SUBS) so one section can't explode
            if not isinstance(raw_sub, dict):
                continue
            try:
                sub = ExtractedSubsection(**raw_sub)
            except ValidationError:
                continue  # drop malformed sub-sections, keep the rest of the section
            subs.append({
                "id": f"{code}.{len(subs) + 1}",
                "title": sub.title,
                "classification": sub.classification,
                "requirement": sub.requirement,
            })
        if not section.requirement and not subs:
            continue  # nothing answerable -- neither a section requirement nor a sub-section
        out.append({
            "id": code,
            "title": section.title,
            "classification": section.classification,
            "requirement": section.requirement,
            "subsections": subs,
        })
    return ensure_unique_codes(out)


def ensure_unique_codes(sections: list[dict]) -> list[dict]:
    """Guarantee unique TOP-LEVEL section codes (and therefore unique sub-section req_ids) BEFORE
    questions are written. The model can emit the same id twice, and the chunked-fallback merge
    (generation._consolidate) keys on normalised title, so two chunks that both returned "B1" with
    different titles would otherwise survive as two top-level sections with the SAME code -- and
    mint colliding "B1.1" req_ids (the export/answer key). A repeated code is suffixed with a
    counter ("B1", then "B1-2", "B1-3", ...) and each section's sub-section ids are re-derived from
    its final code so they stay unique too. Mutates in place and returns the list."""
    used: set[str] = set()
    for sec in sections:
        code = sec["id"]
        if code in used:
            n = 2
            while f"{code}-{n}" in used:
                n += 1
            code = f"{code}-{n}"
        used.add(code)
        sec["id"] = code
        for n, sub in enumerate(sec.get("subsections") or [], start=1):
            sub["id"] = f"{code}.{n}"
    return sections


def extract_requirements(tender_text: str, provider: LLMProvider, *, max_chars: int = MAX_CONTEXT_CHARS,
                         id_prefix: str = "") -> list[dict]:
    """Extract a document-agnostic, COARSE requirements catalogue from raw tender text.

    Returns a list of {id, title, classification, requirement, subsections} dicts, where
    `subsections` is an EXPLICIT (model-returned) list of {id, title, classification, requirement}
    sub-requirements -- so the section+sub-section tree is deterministic on every tender instead of
    depending on whether the model embedded "B1.1"/"(a)" markers in prose. Schema-validated
    (malformed sections and sub-sections dropped individually) and capped at MAX_ITEMS (idg's "at
    most 20 items") TOP-LEVEL sections. Retries up to _MAX_ATTEMPTS times if the model's response
    can't be parsed/validated.

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
            raw_items = _parse_llm_json_array(
                response.text, truncated=getattr(response, "truncated", False))
            out = _validate_sections(raw_items, id_prefix=id_prefix)
            if out:
                return out[:MAX_ITEMS]
            last_error = ExtractionError("no valid requirements after schema validation")
        except ExtractionError as e:
            last_error = e
        except Exception as e:  # noqa: BLE001 - a raw provider timeout/throttle is transient: retry
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
