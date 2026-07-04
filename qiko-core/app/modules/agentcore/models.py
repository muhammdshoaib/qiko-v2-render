"""Core data types for the agentic runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class Requirement:
    """A single thing to answer, with the retrieved evidence for it."""
    id: str
    text: str
    context: list[str] = field(default_factory=list)  # retrieved passages / evidence
    topic: str | None = None


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
