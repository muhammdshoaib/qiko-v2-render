"""Feedback flywheel: human-approved / edited answers become trusted ground truth, scoped by
tenant + topic, and are fed back into future generations. Approved text overrides the AI draft.

In-memory store stands in until the pgvector-backed verified store lands (SCRUM-12). The runtime
depends only on the VerifiedStore protocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class VerifiedStore(Protocol):
    async def add(self, tenant: str, topic: str, text: str) -> None: ...
    async def get(self, tenant: str, topic: str) -> list[str]: ...


@dataclass
class InMemoryVerifiedStore:
    _data: dict[tuple[str, str], list[str]] = field(default_factory=dict)

    async def add(self, tenant: str, topic: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        bucket = self._data.setdefault((tenant, topic), [])
        if text not in bucket:
            bucket.append(text)

    async def get(self, tenant: str, topic: str) -> list[str]:
        return list(self._data.get((tenant, topic), []))
