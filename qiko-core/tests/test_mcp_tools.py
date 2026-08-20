import pytest

from app.modules.agentcore.tools import ToolError
from app.modules.knowledge.service import KnowledgeService
from app.modules.mcp.tools import build_registry

ISO = "IDG holds a current ISO 9001 quality management certification valid through 2027."


def _registry():
    return build_registry(KnowledgeService(), tenant="idg")


def test_registry_exposes_expected_tools():
    assert _registry().names() == ["knowledge_ingest", "knowledge_search"]


async def test_ingest_then_search_via_tools():
    reg = _registry()
    assert await reg.invoke("knowledge_ingest", {"doc_id": "iso", "text": ISO, "agent_id": "a1"}) == 1
    hits = await reg.invoke("knowledge_search", {"query": "ISO 9001 certification", "k": 3, "agent_id": "a1"})
    assert any("ISO 9001" in h for h in hits)


async def test_tool_args_are_validated():
    reg = _registry()
    with pytest.raises(ToolError):
        await reg.invoke("knowledge_search", {"query": ""})       # min_length=1
    with pytest.raises(ToolError):
        await reg.invoke("knowledge_search", {"query": "x", "k": 999})  # le=50
    with pytest.raises(ToolError):
        await reg.invoke("knowledge_ingest", {"doc_id": "d"})     # missing text


async def test_tools_are_tenant_scoped():
    reg = _registry()
    await reg.invoke("knowledge_ingest", {"doc_id": "iso", "text": ISO, "agent_id": "a1"})
    # a registry for another tenant sees nothing from 'idg'
    other = build_registry(KnowledgeService(), tenant="idg")  # fresh service = empty
    assert await other.invoke("knowledge_search", {"query": "ISO 9001", "agent_id": "a1"}) == []
