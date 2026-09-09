"""Accept-or-escalate gate. Auto-accept only when grounding clears the threshold and there are
no hard-fail issues; otherwise escalate to human review."""
from __future__ import annotations

import re

from app.modules.agentcore.models import Critique, Decision

DEFAULT_THRESHOLD = 0.85

# Below this, the writer is telling us it could not answer from what it was given. The output
# contract instructs it to report 0.2 or lower in exactly that case, so this is a small margin
# above the value the prompt asks for.
MIN_CONFIDENCE = 0.35


# QIKO-1087. The output contract tells the writer never to claim the source document lacks
# something, but a prompt only asks. Two false claims still reached a client-facing document: a
# figure reported as "cut off in evidence" whose complete table row was in context, and a form
# reported as "not part of the source document" that is in the document. Confidence was 0.85 on
# the first, so neither the confidence veto nor grounding could catch it: grounding compares the
# answer to the evidence, and a claim ABOUT the corpus has nothing to compare against.
#
# So the contract is enforced here rather than only requested. These patterns are the shapes the
# claims actually took, plus the ones the contract names explicitly, and no more. A false positive
# escalates a good answer to a human, which is recoverable; a false negative puts a false statement
# about the customer's own document in front of a bid team, which is what happened.
#
# Deliberately NOT matched: statements about the evidence rather than the document. "I could not
# find it in the evidence you were given" is what the contract tells the writer to say instead, and
# "the supplied evidence does not contain X" is handled by the confidence veto above, not here.
_SOURCE_CLAIMS = re.compile(
    r"""
      cut[\s-]off                                   # "[2025 figure cut off in evidence]"
    | truncat(?:ed|ion)                              # named in the contract
    | appears?\s+(?:to\s+be\s+)?incomplete          # the gaps note on the same answer
    | not\s+part\s+of\s+the\s+(?:source\s+)?document # "Form B8-2 was not part of the source document"
    | (?:absent|missing)\s+from\s+the\s+(?:source\s+)?document
    | the\s+(?:source\s+)?document\s+(?:does\s+not|doesn't|did\s+not)\s+(?:contain|include)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def claims_about_the_source(*texts: str | None) -> str | None:
    """Return the offending phrase if any text asserts something about the source document.

    The writer only ever sees retrieved passages, never the document, so it is never in a position
    to know what the document contains. Checked across the answer AND the gaps note, because the
    gaps note is where these claims landed and it is shown to the reviewer as the authoritative
    statement of what is missing.
    """
    for text in texts:
        if not text:
            continue
        found = _SOURCE_CLAIMS.search(text)
        if found:
            return found.group(0)
    return None


def decide(critique: Critique, *, threshold: float = DEFAULT_THRESHOLD,
           hard_fail: bool = False, confidence: float | None = None,
           source_claim: str | None = None) -> Decision:
    """Auto-accept only when grounding clears the threshold AND the writer did not disown its own
    answer.

    Grounding alone was not enough. An answer can be perfectly grounded and still be one the
    writer knows is not an answer: on a real tender, "the supplied evidence does not contain
    company incorporation documents" scored 1.00 grounding, because that sentence's words do
    appear in the evidence, and was auto-accepted while self-reporting 0.15 confidence
    (QIKO-1086). Grounding measures whether the prose is traceable to the sources; it cannot
    measure whether the prose answers anything. The writer's own confidence can, and it is
    already parsed and stored, so it costs nothing to honour it here.

    `source_claim` carries the phrase found by claims_about_the_source(), if any. It is passed in
    rather than detected here so the caller decides what text to check (answer plus gaps note).
    """
    if hard_fail:
        return Decision.human_review
    # A claim about the source document is never auto-acceptable, however well grounded and
    # however confident the writer is. Both observed cases would have passed every other check.
    if source_claim:
        return Decision.human_review
    if confidence is not None and confidence < MIN_CONFIDENCE:
        return Decision.human_review
    if critique.grounding >= threshold:
        return Decision.auto_accept
    return Decision.human_review
