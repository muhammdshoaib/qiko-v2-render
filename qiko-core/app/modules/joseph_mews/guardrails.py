"""Shared AI guardrails for the Joseph Mews worker (2 Sep, JM2-1042 follow-on; 3 Sep,
Creator-config wiring).

"Same worker, same config" (Razvan, 2 Sep): signal_summary.py (JM2-1065) and
portfolio_insights.py both generate investor/agent-facing copy from structured facts, and both
need the same invariants JM2-1030 already established for the WhatsApp conversation - English
only, never invent a fact. One place to change them rather than two copies drifting apart.

Not merged into worker.py's _JOE_PROMPT: that string is the client's own verbatim WhatsApp
script (kept as delivered, per JM2-1029's note), a different kind of prompt for a different
kind of task, not a place to splice unrelated instructions into.

3 Sep (Razvan: "ce controleaza cum facem" - we need something that actually controls this, not
a disconnected shell): this module used to be a hardcoded constant only. It is now backed by a
real Creator Agent (tenant="joseph-mews", agent_id="joseph-mews", provisioned via
provision_tenant.py). Once that Agent's Rules/Guardrails/Prompts are edited through the Creator
UI, resolve_guardrails() picks up the edited text on the next call - no redeploy needed. Before
the Agent exists, or if its config carries no behavior entries yet, SHARED_GUARDRAILS below is
the fallback, so generation is never left promptless while someone is still setting the Agent up.
"""

from __future__ import annotations

from app.modules.workers.persona import synthesize_behavior

SHARED_GUARDRAILS = (
    "Always write in English, regardless of the language of any underlying data. "
    "Use ONLY the facts explicitly supplied to you. Never invent a figure, a date, a name, or "
    "a claim that is not present in the supplied data. If the supplied data is insufficient to "
    "say something grounded, say less, not something invented."
)


def resolve_guardrails(agent_config: dict | None) -> str:
    """The Agent's own admin-edited Prompts/Rules/Guardrails (Creator UI) when it has any,
    else SHARED_GUARDRAILS. agent_config is None when the Agent hasn't been provisioned yet or
    the lookup failed - never an error case, just "nothing to override with"."""
    if agent_config:
        behavior = synthesize_behavior(agent_config)
        if behavior:
            return behavior
    return SHARED_GUARDRAILS
