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
    # Position within its document, 0-based. Lets retrieval widen a hit into the contiguous run of
    # text around it, which is how a table spanning several chunks is handed over whole
    # (QIKO-1085). None for a passage predating migration 0050 whose ordinal could not be
    # reconstructed; such a passage is simply not widened.
    ordinal: int | None = None
