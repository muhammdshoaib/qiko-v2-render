"""Joseph Mews "Joe" worker vertical: a WorkerConfig over the shared agentcore + knowledge engines,
scoped to the joseph-mews tenant.

Two client-stated invariants (JM2-1030): Joe answers ONLY in English regardless of the language a
lead writes in, and never states a fact, figure, or availability claim that isn't present in the
retrieved knowledge base. Unknown questions are escalated to a human, never guessed.
"""
from __future__ import annotations

from app.modules.agentcore.gate import DEFAULT_THRESHOLD
from app.modules.workers.config import WorkerConfig

TENANT = "joseph-mews"

_JOE_PROMPT = (
    "You are Joe, the Joseph Mews property-investment WhatsApp assistant. ENGLISH ONLY: always "
    "reply in English, regardless of the language the lead writes in. GROUNDING: only state facts, "
    "figures, availability, or claims present in the retrieved knowledge base. Never invent a "
    "statistic, price, or availability. If a question cannot be answered from the knowledge base, "
    "say so and escalate to a human agent instead of guessing."
)


def joseph_mews_worker_config(*, gate_threshold: float = DEFAULT_THRESHOLD) -> WorkerConfig:
    return WorkerConfig(name="joe-joseph-mews", tenant=TENANT, gate_threshold=gate_threshold,
                        system_prompt=_JOE_PROMPT)
