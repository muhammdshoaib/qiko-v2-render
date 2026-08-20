"""Research brief feature (QIW-1016).

Uses fake pipeline roles so no LLM or external calls are needed.
"""
from __future__ import annotations

import pytest

from app.modules.agentcore.models import Critique
from app.modules.intelligence.models import InMemorySignalStore
from app.modules.intelligence.orchestration import Pipeline
from app.modules.intelligence.orchestration.models import (
    ConsolidatedOutput,
    EvidenceBundle,
    Finding,
    InMemoryPipelineRunStore,
    SpecialistOutput,
    Verdict,
)
from app.modules.intelligence.research import ResearchService
from app.modules.knowledge.service import KnowledgeService


def _fake_pipeline(store: InMemoryPipelineRunStore, *, grounded: bool = True) -> Pipeline:
    class Scout:
        async def gather(self, tenant: str, agent_id: str, subject: str, *, context=None):
            if not grounded:
                return EvidenceBundle()
            return EvidenceBundle(
                text_chunks=["Evidence about the subject."],
                sources=["doc:1"],
            )

    class Specialist:
        async def work(self, evidence: EvidenceBundle, facet: str) -> SpecialistOutput:
            return SpecialistOutput(
                facet=facet,
                answer=f"Answer for {facet}",
                confidence=1.0,
                gaps="",
                citations=["doc:1"],
            )

    class Synthesizer:
        async def consolidate(self, outputs: list[SpecialistOutput]) -> ConsolidatedOutput:
            if not grounded:
                return ConsolidatedOutput(
                    text="I don't have that data.",
                    findings=[],
                    citations=[],
                    gaps="No evidence found for the subject.",
                )
            return ConsolidatedOutput(
                text="Brief summary",
                findings=[
                    Finding(
                        text="Finding one",
                        confidence=1.0,
                        evidence_refs=["doc:1"],
                        gaps="",
                    ),
                ],
                citations=["doc:1"],
                gaps="",
            )

    class Critic:
        async def score(self, output: ConsolidatedOutput, evidence: EvidenceBundle) -> Critique:
            return Critique(grounding=1.0 if grounded else 0.0, issues=[])

    class Magistrate:
        def decide(self, critique: Critique) -> Verdict:
            if critique.grounding >= 0.5:
                return Verdict(verdict="accept", reason="grounded", threshold=0.5)
            return Verdict(verdict="escalate", reason="not grounded", threshold=0.5)

    return Pipeline(
        scout=Scout(),
        specialist=Specialist(),
        synthesizer=Synthesizer(),
        critic=Critic(),
        magistrate=Magistrate(),
        store=store,
    )


@pytest.mark.anyio
async def test_start_research_run_creates_a_research_pipeline_run():
    store = InMemoryPipelineRunStore()
    svc = ResearchService(
        store=store,
        knowledge=KnowledgeService(),
        signal_store=InMemorySignalStore(),
    )

    run = await svc.start("acme", "agent-1", "Acme Corp", ["What do they do?"])

    assert run.tenant == "acme"
    assert run.agent_id == "agent-1"
    assert run.subject == "Acme Corp"
    assert run.facets == ["What do they do?"]
    assert run.status["config"]["kind"] == "research"


@pytest.mark.anyio
async def test_get_brief_returns_in_progress_for_uncompleted_run():
    store = InMemoryPipelineRunStore()
    svc = ResearchService(
        store=store,
        knowledge=KnowledgeService(),
        signal_store=InMemorySignalStore(),
    )

    run = await svc.start("acme", "agent-1", "Acme Corp", ["What do they do?"])
    brief = await svc.get_brief("acme", "agent-1", run.run_id)

    assert brief is not None
    assert brief.status == "in_progress"


@pytest.mark.anyio
async def test_get_brief_returns_cited_findings_after_pipeline_completes():
    store = InMemoryPipelineRunStore()
    pipeline = _fake_pipeline(store)
    svc = ResearchService(
        store=store,
        knowledge=KnowledgeService(),
        signal_store=InMemorySignalStore(),
    )

    run = await svc.start("acme", "agent-1", "Acme Corp", ["What do they do?"])
    await pipeline.resume("acme", "agent-1", run.run_id)

    brief = await svc.get_brief("acme", "agent-1", run.run_id)

    assert brief is not None
    assert brief.status == "draft"
    assert brief.summary == "Brief summary"
    assert len(brief.findings) == 1
    assert brief.findings[0].text == "Finding one"
    assert brief.findings[0].evidence_refs == ["doc:1"]
    assert brief.citations == ["doc:1"]


@pytest.mark.anyio
async def test_accept_brief_ingests_ground_truth_and_signals():
    store = InMemoryPipelineRunStore()
    pipeline = _fake_pipeline(store)
    knowledge = KnowledgeService()
    signal_store = InMemorySignalStore()
    svc = ResearchService(
        store=store,
        knowledge=knowledge,
        signal_store=signal_store,
    )

    run = await svc.start("acme", "agent-1", "Acme Corp", ["What do they do?"])
    await pipeline.resume("acme", "agent-1", run.run_id)

    brief = await svc.accept_brief("acme", "agent-1", run.run_id, actor="alice")

    assert brief is not None
    assert brief.status == "accepted"
    assert brief.accepted_at is not None

    docs = await knowledge.list_documents("acme", agent_id="agent-1")
    assert any(d["doc_id"] == f"research:{run.run_id}" for d in docs)

    signals = await signal_store.list_recent("acme", "agent-1", source="research")
    assert len(signals) == 1
    assert signals[0].kind == "brief"
    assert signals[0].external_id == run.run_id


@pytest.mark.anyio
async def test_get_brief_returns_mostly_gaps_when_no_evidence():
    store = InMemoryPipelineRunStore()
    pipeline = _fake_pipeline(store, grounded=False)
    svc = ResearchService(
        store=store,
        knowledge=KnowledgeService(),
        signal_store=InMemorySignalStore(),
    )

    run = await svc.start("acme", "agent-1", "Unknown Corp", ["What do they do?"])
    await pipeline.resume("acme", "agent-1", run.run_id)

    brief = await svc.get_brief("acme", "agent-1", run.run_id)

    assert brief is not None
    assert brief.status == "draft"
    assert "No evidence found" in brief.gaps
    assert not brief.findings
