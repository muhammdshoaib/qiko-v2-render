from app.modules.agentcore.models import Decision
from app.modules.agentcore.runtime import AgentCore
from app.modules.ai.gateway import StubProvider
from app.modules.agentcore.generator import Generator
from app.modules.knowledge.evaluation import evaluate_document, relevant_sections
from app.modules.knowledge.service import KnowledgeService


def test_relevant_sections_ranks_by_overlap():
    secs = ["ISO 9001 certification held", "office cafeteria menu", "security compliance SOC 2"]
    out = relevant_sections("certification and compliance", secs)
    assert "office cafeteria menu" not in out
    assert any("ISO 9001" in s or "compliance" in s for s in out)


async def test_evaluate_document_is_grounded_and_agentic():
    knowledge = KnowledgeService()
    await knowledge.ingest("acme", "rfp1", "IDG holds ISO 9001 certification valid through 2027.")
    await knowledge.ingest("acme", "rfp1", "Our team has 15 years of audit experience.")
    agent = AgentCore(generator=Generator(provider=StubProvider()))

    result = await evaluate_document(agent, knowledge, "acme", "rfp1",
                                     "Are certifications and compliance evidenced?", topic="rfp")
    # answer is grounded in the document (agentcore gate), not a free-form model call
    assert result.decision is Decision.auto_accept
    assert "ISO 9001" in result.answer
