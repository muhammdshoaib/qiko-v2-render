"""Shared AI guardrails for the Joseph Mews worker (2 Sep, JM2-1042 follow-on).

"Same worker, same config" (Razvan, 2 Sep): signal_summary.py (JM2-1065) and
portfolio_insights.py both generate investor/agent-facing copy from structured facts, and both
need the same invariants JM2-1030 already established for the WhatsApp conversation - English
only, never invent a fact. One place to change them rather than two copies drifting apart.

Not merged into worker.py's _JOE_PROMPT: that string is the client's own verbatim WhatsApp
script (kept as delivered, per JM2-1029's note), a different kind of prompt for a different
kind of task, not a place to splice unrelated instructions into.
"""

from __future__ import annotations

SHARED_GUARDRAILS = (
    "Always write in English, regardless of the language of any underlying data. "
    "Use ONLY the facts explicitly supplied to you. Never invent a figure, a date, a name, or "
    "a claim that is not present in the supplied data. If the supplied data is insufficient to "
    "say something grounded, say less, not something invented."
)
