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
        # agent_id is given, narrows to that worker's own passages (QIK-315) so one worker never
        # retrieves another's knowledge.
        passages = self._by_tenant.get(tenant, [])
        if agent_id is not None:
            passages = [p for p in passages if p.agent_id == agent_id]
        return list(passages)

    async def delete_doc(self, tenant: str, doc_id: str, agent_id: str | None = None) -> int:
        current = self._by_tenant.get(tenant, [])
        kept = [p for p in current
                if p.doc_id != doc_id or (agent_id is not None and p.agent_id != agent_id)]
        self._by_tenant[tenant] = kept
        return len(current) - len(kept)
