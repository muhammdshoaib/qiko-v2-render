"""Vector store with first-class per-tenant isolation (partition key = tenant). In-memory now;
the pgvector-backed store slots in behind the same protocol (HNSW index, same tenant filter)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.knowledge.models import Passage


class VectorStore(Protocol):
    async def add(self, passage: Passage) -> None: ...
    async def get(self, tenant: str, agent_id: str | None = None) -> list[Passage]: ...
    async def delete_doc(self, tenant: str, doc_id: str, agent_id: str | None = None) -> int: ...


@dataclass
class InMemoryVectorStore:
    _by_tenant: dict[str, list[Passage]] = field(default_factory=dict)

    async def add(self, passage: Passage) -> None:
        self._by_tenant.setdefault(passage.tenant, []).append(passage)

    async def get(self, tenant: str, agent_id: str | None = None) -> list[Passage]:
        # Only ever returns the caller tenant's passages; cross-tenant reads are impossible. When an
        # agent_id is given, return that worker's own passages plus legacy tenant-wide passages
        # (agent_id=None) so shared knowledge is not orphaned by worker-scoped retrieval.
        passages = self._by_tenant.get(tenant, [])
        if agent_id is not None:
            passages = [p for p in passages if p.agent_id == agent_id or p.agent_id is None]
        return list(passages)

    async def delete_doc(self, tenant: str, doc_id: str, agent_id: str | None = None) -> int:
        current = self._by_tenant.get(tenant, [])
        kept = [p for p in current if not (p.doc_id == doc_id and p.agent_id == agent_id)]
        self._by_tenant[tenant] = kept
        return len(current) - len(kept)
