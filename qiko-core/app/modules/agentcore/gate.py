"""Accept-or-escalate gate. Auto-accept only when grounding clears the threshold and there are
no hard-fail issues; otherwise escalate to human review."""
from __future__ import annotations

from app.modules.agentcore.models import Critique, Decision

DEFAULT_THRESHOLD = 0.85


def decide(critique: Critique, *, threshold: float = DEFAULT_THRESHOLD,
           hard_fail: bool = False) -> Decision:
    if hard_fail:
        return Decision.human_review
    if critique.grounding >= threshold:
        return Decision.auto_accept
    return Decision.human_review
