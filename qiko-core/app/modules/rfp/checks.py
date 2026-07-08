"""Guardrail checks for a drafted answer, independent of the LLM grounding gate.

Port of idg-worker's app/agents/checks.py (added after a real customer review flagged two
concrete failure modes an LLM grounding check alone doesn't catch):

1. stale_dates    - a validity/expiry date quoted in an answer that's already in the past
                    (e.g. "ISO 9001 certificate valid until 19 May 2025" submitted after that date).
2. applicability  - a requirement that reads like a generic/templated item that may not actually
                    apply to this bidder's line of work, worth a clarification question rather
                    than a drafted answer.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_MONTHS = "january february march april may june july august september october november december".split()
_M = "|".join(_MONTHS)
_EXPIRY_KEYWORDS = ("valid until", "valid to", "valid through", "valid up to", "expiry", "expires",
                   "expire", "expiration", "renewal due", "certificate is valid", "certification is valid")


def _parse_dates(text: str) -> list[tuple[date, str, int]]:
    """Find "day month year", "month year", and ISO dates. A "month year" match that's actually
    part of a longer "day month year" span (e.g. the "May 2025" inside "19 May 2025") is dropped
    so the same date isn't reported twice with two different day-of-month guesses."""
    spans: list[tuple[int, int]] = []
    out: list[tuple[date, str, int]] = []

    for m in re.finditer(rf"\b(\d{{1,2}})\s+({_M})\s+(\d{{4}})\b", text, re.I):
        try:
            out.append((datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date(),
                       m.group(0), m.start()))
            spans.append(m.span())
        except ValueError:
            pass
    for m in re.finditer(rf"\b({_M})\s+(\d{{4}})\b", text, re.I):
        if any(s <= m.start() and m.end() <= e for s, e in spans):
            continue
        try:
            out.append((datetime.strptime(f"1 {m.group(1)} {m.group(2)}", "%d %B %Y").date(),
                       m.group(0), m.start()))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        try:
            out.append((date(int(m.group(1)), int(m.group(2)), int(m.group(3))), m.group(0), m.start()))
        except ValueError:
            pass
    return out


def stale_dates(text: str, today: date | None = None) -> list[dict]:
    """Return past dates presented in a validity/expiry context (the risky ones) -- a date that
    merely appears in the text (e.g. a past project's completion date) is not flagged."""
    today = today or date.today()
    text = text or ""
    low = text.lower()
    findings = []
    for d, raw, pos in _parse_dates(text):
        if d >= today:
            continue
        ctx = low[max(0, pos - 70):pos + len(raw) + 15]
        if any(k in ctx for k in _EXPIRY_KEYWORDS):
            findings.append({
                "date": raw, "iso": d.isoformat(),
                "note": f"Validity/expiry date {raw} is in the past ({d.isoformat()}); "
                        "confirm the current certificate/date before submission.",
            })
    seen: set[tuple[str, str]] = set()
    uniq = []
    for f in findings:
        key = (f["iso"], f["date"])
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


# Generic construction/works-template vocabulary that suggests a requirement may not apply to
# every bidder's actual scope of work (e.g. a security-services bidder answering a civil-works
# item). Kept intentionally generic/reusable rather than tied to one tender's own numbering.
_TEMPLATE_KEYWORDS = ("ready mix", "ready-mix", "concrete", "manufacturing", "as-built", "as built",
                     "red lining", "red-lining", "redline", "inspection and testing plan", "itp",
                     "mechanical equipment", "plant and equipment", "plant & equipment",
                     "materials inspection")


def applicability(requirement: str) -> tuple[str, str]:
    """Returns ("applicable", "") or ("possibly_not_applicable", suggestion)."""
    hay = (requirement or "").lower()
    if any(k in hay for k in _TEMPLATE_KEYWORDS):
        return ("possibly_not_applicable",
                "Reads like a generic works-template requirement that may not apply to this "
                "bidder's actual scope. Decide: answer as written, mark not applicable, or raise "
                "a clarification with the buyer.")
    return ("applicable", "")


def run_checks(requirement: str, answer: str) -> dict:
    """Run both guardrails for one requirement/answer pair; used to annotate export rows and
    the review UI without gating the answer itself (these are advisory, not a hard pass/fail)."""
    applicable, suggestion = applicability(requirement)
    return {
        "stale_dates": stale_dates(answer),
        "applicability": applicable,
        "applicability_note": suggestion,
    }
