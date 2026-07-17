"""Core data types for the agentic runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class Requirement:
    """A single thing to answer, with the retrieved evidence for it."""
    id: str
    text: str
    context: list[str] = field(default_factory=list)  # retrieved passages / evidence (prompt text)
    topic: str | None = None
    # Clean SOURCE LABELS for the retrieved evidence (doc_id + a short snippet), deduped by
    # document. These become AgentResult.citations so a UI enumerates "N Sources" from document
    # names, NOT the raw multi-KB passage bodies. Empty for callers that build a Requirement
    # directly (the runtime then falls back to `context`).
    sources: list[str] = field(default_factory=list)


@dataclass
class Critique:
    grounding: float          # 0..1 fraction of the answer supported by the evidence
    issues: list[str] = field(default_factory=list)


class Decision(str, Enum):
    auto_accept = "auto_accept"
    human_review = "human_review"


@dataclass
class AgentResult:
    requirement_id: str
    answer: str
    critique: Critique
    decision: Decision
    citations: list[str] = field(default_factory=list)
    # The writer's self-reported confidence (0..1): how well the evidence let it answer. Distinct
    # from critique.grounding (the independent check of how much of the prose the evidence backs);
    # falls back to the grounding score when the generator did not self-report one.
    confidence: float = 0.0
    # Short note of what the evidence did not let the writer support ("" when nothing is missing).
    gaps: str = ""
    # True when the answer came from the StubProvider fallback (not a real grounded draft) -- lets
    # persistence paths refuse to store it as a ready answer. See rfp.router._generate_question.
    stub: bool = False
