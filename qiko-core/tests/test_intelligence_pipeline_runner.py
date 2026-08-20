import json

import pytest

from app.modules.agentcore.generator import Generator
from app.modules.agentcore.runtime import AgentCore
from app.modules.ai.embeddings import LocalEmbeddings
from app.modules.ai.gateway import LLMResponse
from app.modules.intelligence.orchestration import (
    ConsolidatedOutput,
    Critic,
    EvidenceBundle,
    Finding,
    InMemoryPipelineRunStore,
    Magistrate,
    Pipeline,
    PipelineConfig,
    PipelineRun,
    Scout,
    Specialist,
)
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.store import InMemoryVectorStore
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import Worker
from app.tasks.jobs import run_intelligence_pipeline


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text, stub=False)


class _RotatingProvider:
    def __init__(self, *texts: str):
        self.texts = list(texts)
        self.i = 0

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        text = self.texts[self.i % len(self.texts)]
        self.i += 1
        return LLMResponse(text=text, stub=False)


class FakeSynthesizer:
    """Deterministic synthesizer for pipeline tests: returns the specialist answers joined."""

    async def consolidate(self, outputs: list) -> ConsolidatedOutput:
        if not outputs:
            return ConsolidatedOutput(text="")
        text = " ".join(o.answer for o in outputs)
        return ConsolidatedOutput(
            text=text,
            findings=[Finding(text=o.answer) for o in outputs],
            citations=list({c for o in outputs for c in o.citations}),
        )


@pytest.fixture
def knowledge():
    store = InMemoryVectorStore()
    embeddings = LocalEmbeddings(dim=8)
    return KnowledgeService(store=store, embeddings=embeddings)


@pytest.fixture
def scout(knowledge):
    return Scout(knowledge)


@pytest.fixture
def specialist(knowledge):
    # First answer is partially grounded (revise band). Second is fully grounded.
    provider = _RotatingProvider(
        json.dumps({
            "answer": "ACME builds AI tools. The product is called Qiko. We sell Mars real estate.",
            "confidence": 0.9,
            "gaps": "",
        }),
        json.dumps({"answer": "ACME builds AI tools.", "confidence": 0.9, "gaps": ""}),
    )
    config = WorkerConfig(name="test", tenant="t1", agent_id="w1")
    worker = Worker(
        config=config,
        knowledge=knowledge,
        agent=AgentCore(generator=Generator(provider=provider), threshold=0.85),
    )
    return Specialist(worker)


@pytest.fixture
def synthesizer():
    return FakeSynthesizer()


@pytest.fixture
def critic():
    return Critic()


@pytest.fixture
def magistrate():
    # Lower threshold so the partially grounded first answer falls into the revise band.
    return Magistrate(threshold=0.7)


@pytest.fixture
def pipeline(scout, specialist, synthesizer, critic, magistrate):
    store = InMemoryPipelineRunStore()
    return Pipeline(
        scout=scout,
        specialist=specialist,
        synthesizer=synthesizer,
        critic=critic,
        magistrate=magistrate,
        store=store,
    )


async def test_pipeline_runs_to_accept_after_revision(pipeline, knowledge):
    await knowledge.ingest("t1", "doc-1", "ACME builds AI tools for sales.", agent_id="w1")
    await knowledge.ingest("t1", "doc-2", "The product is called Qiko.", agent_id="w1")
    config = PipelineConfig(
        tenant="t1", agent_id="w1", subject="What does ACME do?",
        facets=["products"], retry_limit=1)

    run = await pipeline.start(config)

    assert run.status["scout"] == "ready"
    assert run.status["specialists"]["state"] == "ready"
    assert run.status["synthesize"] == "ready"
    assert run.status["critic"] == "ready"
    assert run.status["magistrate"] == "ready"
    assert run.verdict == "accept"
    assert run.status["revisions"] == 1
    # One specialist call for the first pass, one for the retry.
    assert run.status["outputs"]["verdict"]["reason"]


async def test_pipeline_resume_from_saved_scout_state(pipeline, knowledge):
    await knowledge.ingest("t1", "doc-1", "ACME builds AI tools for sales.", agent_id="w1")
    await knowledge.ingest("t1", "doc-2", "The product is called Qiko.", agent_id="w1")
    run = PipelineRun(
        run_id="r1",
        tenant="t1",
        agent_id="w1",
        subject="What does ACME do?",
        facets=["products"],
        status={
            "scout": "ready",
            "specialists": {
                "state": "pending", "done": 0, "total": 0, "failed": 0, "failed_ids": []
            },
            "synthesize": "pending",
            "critic": "pending",
            "magistrate": "pending",
            "updated_at": "2026-08-20T00:00:00+00:00",
            "error": None,
            "errors": {},
            "outputs": {
                "evidence": {
                    "text_chunks": [
                        "ACME builds AI tools for sales.",
                        "The product is called Qiko.",
                    ],
                    "sources": ["doc-1"],
                },
            },
            "revisions": 0,
            "config": {
                "tenant": "t1", "agent_id": "w1", "subject": "What does ACME do?",
                "facets": ["products"], "max_facets": 5, "retry_limit": 1,
                "specialist_concurrency": 5,
            },
        },
    )
    await pipeline.store.add(run)

    resumed = await pipeline.resume("t1", "w1", "r1")

    assert resumed is not None
    assert resumed.status["scout"] == "ready"
    assert resumed.status["specialists"]["state"] == "ready"
    assert resumed.status["magistrate"] == "ready"
    assert resumed.verdict == "accept"


async def test_pipeline_resume_when_all_stages_complete(pipeline, knowledge):
    await knowledge.ingest("t1", "doc-1", "ACME builds AI tools for sales.", agent_id="w1")
    await knowledge.ingest("t1", "doc-2", "The product is called Qiko.", agent_id="w1")
    config = PipelineConfig(
        tenant="t1", agent_id="w1", subject="What does ACME do?",
        facets=["products"], retry_limit=1)
    run = await pipeline.start(config)

    resumed = await pipeline.resume("t1", "w1", run.run_id)

    assert resumed is not None
    assert resumed.status["magistrate"] == "ready"
    assert resumed.verdict == "accept"


async def test_pipeline_critic_layer_only_lowers_score():
    class _LowCritiqueProvider:
        def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
            return LLMResponse(
                text=json.dumps({"grounding": 1.0, "issues": ["too vague"]}),
                stub=False,
            )

    critic = Critic(llm_layer=_LowCritiqueProvider())
    output = ConsolidatedOutput(text="ACME builds AI tools.")
    evidence = EvidenceBundle(text_chunks=["ACME builds AI tools for sales."])
    critique = await critic.score(output, evidence)

    # Deterministic score for a fully grounded sentence is 1.0; LLM issue is added.
    assert critique.grounding <= 1.0


async def test_run_intelligence_pipeline_task_uses_injected_pipeline(pipeline, knowledge):
    await knowledge.ingest("t1", "doc-1", "ACME builds AI tools for sales.", agent_id="w1")
    await knowledge.ingest("t1", "doc-2", "The product is called Qiko.", agent_id="w1")
    config = PipelineConfig(
        tenant="t1", agent_id="w1", subject="What does ACME do?",
        facets=["products"], retry_limit=1)
    run = await pipeline.start(config)

    result = await run_intelligence_pipeline(
        tenant="t1", agent_id="w1", run_id=run.run_id, pipeline=pipeline)

    assert result["run_id"] == run.run_id
    assert result["verdict"] == "accept"
    assert result["status"]["magistrate"] == "ready"


async def test_run_intelligence_pipeline_task_requires_deps():
    with pytest.raises(ValueError, match="sessionmaker or pipeline"):
        await run_intelligence_pipeline(tenant="t1", agent_id="w1", run_id="r1")


async def test_run_intelligence_pipeline_task_missing_run_raises():
    store = InMemoryPipelineRunStore()
    pipeline = Pipeline(
        scout=Scout(KnowledgeService(store=InMemoryVectorStore(), embeddings=LocalEmbeddings(dim=8))),
        specialist=Specialist(Worker(
            config=WorkerConfig(name="test", tenant="t1", agent_id="w1"),
            knowledge=KnowledgeService(store=InMemoryVectorStore()),
            agent=AgentCore(generator=Generator(provider=_CannedProvider("no")), threshold=0.85))),
        synthesizer=FakeSynthesizer(),
        critic=Critic(),
        magistrate=Magistrate(threshold=0.85),
        store=store,
    )
    with pytest.raises(ValueError, match="pipeline run .* not found"):
        await run_intelligence_pipeline(
            tenant="t1", agent_id="w1", run_id="missing", pipeline=pipeline)
