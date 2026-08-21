"""Platform tools exposed to agents through the shared ToolRegistry with Pydantic-validated
arguments. These are the callable capabilities (knowledge, Excel-as-knowledge, Signal); the
Python MCP SDK server (server.py) simply surfaces this registry over MCP."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.agentcore.tools import ToolRegistry
from app.modules.knowledge.service import KnowledgeService


class SearchArgs(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    agent_id: str = Field(min_length=1)


class IngestArgs(BaseModel):
    doc_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)


def build_registry(knowledge: KnowledgeService, tenant: str) -> ToolRegistry:
    """Build a tenant-scoped tool registry. Excel analysis is ingested as knowledge, so it is
    searchable through the same knowledge_search tool (Excel = a knowledge sub-feature).

    Every knowledge tool requires an agent_id so an agent can only read or write its own worker
    corpus (plus the shared tenant-wide corpus that retrieve includes for worker-scoped queries)."""
    reg = ToolRegistry()

    @reg.register("knowledge_search", SearchArgs)
    async def _search(a: SearchArgs) -> list[str]:
        return [p.text for p in await knowledge.retrieve(tenant, a.query, k=a.k, agent_id=a.agent_id)]

    @reg.register("knowledge_ingest", IngestArgs)
    async def _ingest(a: IngestArgs) -> int:
        return await knowledge.ingest(tenant, a.doc_id, a.text, agent_id=a.agent_id)

    return reg
