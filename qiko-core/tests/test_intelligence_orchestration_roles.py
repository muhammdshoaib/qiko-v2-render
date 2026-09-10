import json

import pytest

from app.modules.agentcore.models import Critique
from app.modules.agentcore.generator import Generator
from app.modules.agentcore.runtime import AgentCore
from app.modules.ai.embeddings import LocalEmbeddings
from app.modules.ai.gateway import LLMResponse
from app.modules.intelligence.documents import Document, InMemoryDocumentStore
from app.modules.intelligence.models import InMemorySignalStore, Signal
from app.modules.intelligence.orchestration import (
    ConsolidatedOutput,
    Critic,
    EvidenceBundle,
    Magistrate,
    Scout,
    Specialist,
    SpecialistOutput,
    Synthesizer,
)
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.store import InMemoryVectorStore
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import Worker


class _CannedProvider:
    """Returns a fixed text, optionally recording the prefill it was called with."""

    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text, stub=False)


class _RecordingProvider:
    """Returns a fixed text and records the kwargs each call was made with."""

    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        self.calls.append({"temperature": temperature})
        return LLMResponse(text=self.text, stub=False)


@pytest.fixture
def knowledge():
    store = InMemoryVectorStore()
    embeddings = LocalEmbeddings(dim=8)
    return KnowledgeService(store=store, embeddings=embeddings)


@pytest.fixture
def signal_store():
    return InMemorySignalStore()


@pytest.fixture
def document_store():
    return InMemoryDocumentStore()


@pytest.fixture
def worker(knowledge):
    config = WorkerConfig(name="test", tenant="t1", agent_id="w1")
    generator = Generator(provider=_CannedProvider(
        json.dumps({"answer": "ACME builds AI tools.", "confidence": 0.9, "gaps": ""})))
    return Worker(config=config, knowledge=knowledge,
                  agent=AgentCore(generator=generator, threshold=0.85))


async def _ingest(knowledge, tenant, agent_id, doc_id, text):
    return await knowledge.ingest(tenant, doc_id, text, agent_id=agent_id)


def _signal(**overrides) -> Signal:
    base = dict(
        tenant="t1", agent_id="w1", source="slack", kind="message",
        external_id="ev-1", container="T1/C1", actor="U1",
        title="progress", body="we shipped the dashboard",
        occurred_at="2026-08-01T12:00:00+00:00",
    )
    base.update(overrides)
    return Signal(**base)


async def test_scout_gathers_knowledge_signals_and_documents(knowledge, signal_store, document_store):
    await _ingest(knowledge, "t1", "w1", "doc-1", "ACME builds AI tools for sales teams.")
    await signal_store.add(_signal(external_id="s1", url="https://example.invalid/1"))
    await document_store.add(Document(
        doc_id="upload-1", tenant="t1", agent_id="w1", filename="readme.txt",
        content_type="text/plain", size=12, storage_key="x"))

    scout = Scout(knowledge, signal_store=signal_store, document_store=document_store,
                  retrieval_k=3, signal_limit=10)
    bundle = await scout.gather("t1", "w1", "What does ACME build?")

    assert any("AI tools" in chunk for chunk in bundle.text_chunks)
    assert any("shipped the dashboard" in chunk for chunk in bundle.text_chunks)
    assert any("readme.txt" in chunk for chunk in bundle.text_chunks)
    assert "doc-1" in bundle.sources
    assert "https://example.invalid/1" in bundle.sources
    assert "upload-1" in bundle.sources


async def test_scout_includes_extra_context(knowledge):
    scout = Scout(knowledge)
    bundle = await scout.gather("t1", "w1", "What does ACME build?", context=["custom context"])
    assert "custom context" in bundle.text_chunks


async def test_specialist_calls_worker_and_returns_output(worker):
    bundle = EvidenceBundle(text_chunks=["ACME builds AI tools."], sources=["doc-1"])
    specialist = Specialist(worker)
    out = await specialist.work(bundle, "What does ACME build?")

    assert out.facet == "What does ACME build?"
    assert out.answer == "ACME builds AI tools."
    assert out.confidence == 0.9
    assert out.gaps == ""


async def test_synthesizer_parses_json_summary_and_findings():
    payload = json.dumps({
        "summary": "ACME builds AI-powered sales tools.",
        "findings": [
            {"text": "AI tools", "gaps": ""},
            {"text": "sales focus", "gaps": "no market size"},
        ],
        "citations": ["doc-1"],
    })
    synthesizer = Synthesizer(Generator(provider=_CannedProvider(payload)))
    outputs = [
        SpecialistOutput(facet="products", answer="AI tools", confidence=0.9, gaps=""),
        SpecialistOutput(facet="market", answer="sales", confidence=0.8, gaps="size unknown"),
    ]
    result = await synthesizer.consolidate(outputs)

    assert result.text == "ACME builds AI-powered sales tools."
    assert [f.text for f in result.findings] == ["AI tools", "sales focus"]
    assert result.findings[1].gaps == "no market size"
    assert result.citations == ["doc-1"]


async def test_synthesizer_parses_evidence_refs_per_finding():
    payload = json.dumps({
        "summary": "ACME builds AI-powered sales tools.",
        "findings": [
            {
                "text": "AI tools",
                "evidence_refs": ["doc-1", "doc-2"],
                "gaps": "",
            },
        ],
        "citations": ["doc-1", "doc-2"],
    })
    synthesizer = Synthesizer(Generator(provider=_CannedProvider(payload)))
    outputs = [
        SpecialistOutput(facet="products", answer="AI tools", confidence=0.9, gaps=""),
    ]
    result = await synthesizer.consolidate(outputs)

    assert result.findings[0].evidence_refs == ["doc-1", "doc-2"]


async def test_synthesizer_returns_raw_text_when_not_json():
    synthesizer = Synthesizer(Generator(provider=_CannedProvider("plain summary")))
    outputs = [SpecialistOutput(facet="x", answer="y", confidence=None, gaps="")]
    result = await synthesizer.consolidate(outputs)

    assert result.text == "plain summary"
    assert result.findings == []


async def test_synthesizer_pins_temperature_zero():
    payload = json.dumps({"summary": "x", "findings": [], "citations": []})
    provider = _RecordingProvider(payload)
    synthesizer = Synthesizer(Generator(provider=provider))
    outputs = [SpecialistOutput(facet="f", answer="a", confidence=0.9, gaps="")]

    await synthesizer.consolidate(outputs)

    assert provider.calls[-1]["temperature"] == 0.0


async def test_critic_uses_deterministic_grounding():
    critic = Critic()
    output = ConsolidatedOutput(text="ACME builds AI tools.")
    evidence = EvidenceBundle(text_chunks=["ACME builds AI tools for sales."])
    critique = await critic.score(output, evidence)

    assert isinstance(critique, Critique)
    assert critique.grounding > 0.0
    assert critique.grounding <= 1.0


async def test_critic_llm_layer_cannot_raise_grounding():
    llm = _CannedProvider(json.dumps({"grounding": 1.0, "issues": ["unrelated issue"]}))
    critic = Critic(llm_layer=llm)
    output = ConsolidatedOutput(text="ACME builds AI tools.")
    evidence = EvidenceBundle(text_chunks=["ACME builds AI tools for sales."])
    critique = await critic.score(output, evidence)

    assert critique.grounding <= 1.0
    assert "unrelated issue" in critique.issues


async def test_critic_llm_layer_pins_temperature_zero():
    llm = _RecordingProvider(json.dumps({"grounding": 1.0, "issues": []}))
    critic = Critic(llm_layer=llm)
    output = ConsolidatedOutput(text="ACME builds AI tools.")
    evidence = EvidenceBundle(text_chunks=["ACME builds AI tools for sales."])

    await critic.score(output, evidence)

    assert llm.calls[-1]["temperature"] == 0.0


async def test_magistrate_accept_when_grounding_high():
    magistrate = Magistrate(threshold=0.85)
    verdict = magistrate.decide(Critique(grounding=0.9, issues=[]))
    assert verdict.verdict == "accept"


async def test_magistrate_revise_when_close_and_issues():
    magistrate = Magistrate(threshold=0.85)
    verdict = magistrate.decide(Critique(grounding=0.82, issues=["missing date"]))
    assert verdict.verdict == "revise"


async def test_magistrate_escalate_when_far_below():
    magistrate = Magistrate(threshold=0.85)
    verdict = magistrate.decide(Critique(grounding=0.5, issues=[]))
    assert verdict.verdict == "escalate"
