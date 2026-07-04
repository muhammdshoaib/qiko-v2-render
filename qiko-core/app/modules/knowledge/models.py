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
