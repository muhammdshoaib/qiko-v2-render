"""Accept-or-escalate gate. Auto-accept only when grounding clears the threshold and there are
no hard-fail issues; otherwise escalate to human review."""
from __future__ import annotations

from app.modules.agentcore.models import Critique, Decision

DEFAULT_THRESHOLD = 0.85

# Below this, the writer is telling us it could not answer from what it was given. The output
# contract instructs it to report 0.2 or lower in exactly that case, so this is a small margin
# above the value the prompt asks for.
MIN_CONFIDENCE = 0.35


def decide(critique: Critique, *, threshold: float = DEFAULT_THRESHOLD,
           hard_fail: bool = False, confidence: float | None = None) -> Decision:
    """Auto-accept only when grounding clears the threshold AND the writer did not disown its own
    answer.

    Grounding alone was not enough. An answer can be perfectly grounded and still be one the
    writer knows is not an answer: on a real tender, "the supplied evidence does not contain
    company incorporation documents" scored 1.00 grounding, because that sentence's words do
    appear in the evidence, and was auto-accepted while self-reporting 0.15 confidence
    (QIKO-1086). Grounding measures whether the prose is traceable to the sources; it cannot
    measure whether the prose answers anything. The writer's own confidence can, and it is
    already parsed and stored, so it costs nothing to honour it here.
    """
    if hard_fail:
        return Decision.human_review
    if confidence is not None and confidence < MIN_CONFIDENCE:
        return Decision.human_review
    if critique.grounding >= threshold:
        return Decision.auto_accept
    return Decision.human_review
