"""Independent grounding critic.

Scores how much of an answer is supported by the supplied evidence, deterministically, so the
gate never relies on the same model that wrote the answer. A sentence is 'grounded' when enough
of its content words appear in the evidence. This mirrors the anti-hallucination gate proven in
the IDG worker; an LLM-based critic can be layered on top later behind the same interface.
"""
from __future__ import annotations

import re

from app.modules.agentcore.models import Critique

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "be",
    "will", "we", "our", "that", "this", "as", "by", "at", "it", "its", "from", "have", "has",
}
_SENT = re.compile(r"[^.!?\n]+[.!?]?")
_WORD = re.compile(r"[a-z0-9]+")


def _content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2]


def grounding_score(answer: str, evidence: list[str], *, min_sentence_support: float = 0.6) -> Critique:
    """A sentence counts as grounded when ONE passage supports enough of its content words.

    It used to be scored against the union of every passage's words, which made the score rise
    with the number of passages retrieved rather than with the quality of the answer: a sentence
    could be assembled from a word here and a word there and still clear the bar, so raising
    `retrieval_k` pushed grounding to 1.0 and silently disabled the gate (QIKO-1086). Measured on
    a real tender, going from k=5 to k=30 turned nine of fourteen escalations into auto-accepts.

    Per-passage support is also the honest reading of "grounded": a claim should be traceable to
    a source, not to a word cloud assembled from all of them. The cost is that a sentence which
    genuinely synthesises two passages now scores as ungrounded, which is deliberate. That is a
    claim no single source backs, and it is exactly the kind a reviewer should see.
    """
    passage_words = [set(_content_words(e)) for e in evidence]

    sentences = [s.strip() for s in _SENT.findall(answer) if s.strip()]
    if not sentences:
        return Critique(grounding=0.0, issues=["empty answer"])

    grounded = 0
    issues: list[str] = []
    for sent in sentences:
        words = _content_words(sent)
        if not words:
            grounded += 1  # no factual content to ground (e.g. a connective sentence)
            continue
        best = max((sum(1 for w in words if w in ev) / len(words) for ev in passage_words),
                   default=0.0)
        if best >= min_sentence_support:
            grounded += 1
        else:
            issues.append(sent)

    return Critique(grounding=round(grounded / len(sentences), 3), issues=issues)
