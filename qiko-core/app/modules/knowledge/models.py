"""Knowledge layer data types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Passage:
    id: str
    tenant: str
    doc_id: str
    text: str
    embedding: list[float] = field(default_factory=list)
    score: float = 0.0
    # Which worker this passage belongs to. None = legacy tenant-wide (pre agent-scoping). Retrieval
    # for a specific worker filters on this so one worker never answers from another's knowledge.
    agent_id: str | None = None
