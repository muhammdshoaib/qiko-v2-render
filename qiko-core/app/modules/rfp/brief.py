"""Tender Brief: summarise scope/rules/format/dates and flag likely gaps, grounded in the tender.

Port of idg-worker's pipeline/build_brief.py, generalized to any tender document.

Structured + schema-validated (Pydantic) with retries, mirroring the hardening applied to
requirements extraction (app/modules/rfp/extraction.py): the model response is parsed out of any
prose/markdown, validated against a schema (malformed list entries dropped individually rather than
failing the whole brief), and a bad response gets a retry before surfacing as a BriefError. The
OUTPUT SHAPE is unchanged -- the same {summary, scope, submission_format, key_dates,
success_criteria, gaps_and_risks} dict the endpoint persists and the FE `TenderBrief` type consumes.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.modules.ai.gateway import LLMProvider

SYSTEM = (
    "You are a bid manager. Read the tender text and produce a structured brief. Return ONLY a "
    "JSON object (no prose, no markdown fences) with exactly these keys: "
    '"summary" (3-4 sentences), "scope" (string), "submission_format" (string), '
    '"key_dates" (array of strings), "success_criteria" (array of strings), '
    '"gaps_and_risks" (array of strings).'
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_MAX_ATTEMPTS = 2


class BriefError(Exception):
    pass


def _as_str(v) -> str:
    """Coerce a scalar to a string the way the previous `str(...)` calls did, so a model that
    returns a number/None for a string field still yields the same output rather than failing
    validation outright."""
    return "" if v is None else str(v)


def _clean_str_list(raw) -> list[str]:
    """Drop malformed (non-scalar / empty) entries from a list field, keeping the valid ones and
    coercing/trimming each to a non-empty string -- one bad element can't sink the whole list."""
    out: list[str] = []
    for x in raw or []:
        if isinstance(x, (dict, list)):
            continue  # a nested object/array isn't a valid key-date / criterion / gap string
        s = _as_str(x).strip()
        if s:
            out.append(s)
    return out


class TenderBriefModel(BaseModel):
    """The tender brief's schema. Keys/shape match the endpoint's existing return dict and the FE
    `TenderBrief` type EXACTLY: three string fields plus three string-array fields. `summary` is
    the one required field (an empty summary is not a usable brief); the list fields default to []
    and have their malformed entries dropped in _validate_brief."""
    summary: str  # required: an empty/missing summary fails validation (see validator)
    scope: str = ""
    submission_format: str = ""
    key_dates: list = Field(default_factory=list)
    success_criteria: list = Field(default_factory=list)
    gaps_and_risks: list = Field(default_factory=list)

    @field_validator("summary", "scope", "submission_format", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _as_str(v)

    @field_validator("summary")
    @classmethod
    def _check_summary(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty summary")
        return v

    @field_validator("scope", "submission_format")
    @classmethod
    def _trim(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("key_dates", "success_criteria", "gaps_and_risks", mode="before")
    @classmethod
    def _default_list(cls, v):
        return v if isinstance(v, list) else []


def _parse_llm_json_object(text: str) -> dict:
    """LLMs often wrap JSON in prose or markdown fences; pull out the first object and parse it."""
    match = _JSON_OBJECT.search(text)
    candidate = match.group(0) if match else text
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise BriefError(f"model did not return valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise BriefError("model did not return a JSON object")
    return parsed


def _validate_brief(data: dict) -> dict:
    """Validate the parsed object against TenderBriefModel and return the SAME output dict the
    endpoint has always returned. Raises ValidationError (caught by the retry loop) if the object
    can't produce a usable brief (e.g. no summary)."""
    model = TenderBriefModel(**data)
    return {
        "summary": model.summary,
        "scope": model.scope,
        "submission_format": model.submission_format,
        "key_dates": _clean_str_list(model.key_dates),
        "success_criteria": _clean_str_list(model.success_criteria),
        "gaps_and_risks": _clean_str_list(model.gaps_and_risks),
    }


# 160k (vs the old 60k): the brief's key dates + success criteria + gaps frequently live deep in
# the pack (annex templates, later schedules, tables now that docx tables are extracted), so a
# 60k window silently dropped them for large tenders. Output stays a small JSON object, so the
# larger input is well within the model's context / read timeout.
def extract_brief(tender_text: str, provider: LLMProvider, *, max_chars: int = 160_000) -> dict:
    """Extract the tender brief, schema-validated with retries. Returns the same
    {summary, scope, submission_format, key_dates, success_criteria, gaps_and_risks} dict as before
    (the persisted brief + FE `TenderBrief` type are unchanged). Retries up to _MAX_ATTEMPTS times
    if the model's response can't be parsed/validated; raises BriefError only if still invalid."""
    truncated = tender_text[:max_chars]
    last_error: Exception | None = None
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            response = provider.generate(f"TENDER DOCUMENT:\n{truncated}", system=SYSTEM, temperature=0.0)
            data = _parse_llm_json_object(response.text)
            return _validate_brief(data)
        except BriefError as e:
            last_error = e
        except ValidationError as e:
            last_error = BriefError(f"model response failed schema validation: {e}")
    raise last_error or BriefError("no usable brief could be extracted from this document")
