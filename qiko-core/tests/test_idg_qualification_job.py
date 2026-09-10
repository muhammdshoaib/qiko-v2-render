"""Task 3 gate fixes for run_idg_qualification_pipeline (app.tasks.jobs):

1. LLM10/A09 - the job must open a usage-tracking scope around the pipeline run, exactly like its
   sibling run_intelligence_pipeline, so Specialist/Synthesizer model calls are actually accounted
   for (see app.modules.ai.usage.record's "no scope open" fallback) instead of being silently
   dropped and PipelineRun.cost staying unset.
2. LLM06/A09 - an "accept" verdict that autonomously promotes an opportunity's stage from
   awaiting_review to qualified must leave a durable, queryable activity-log entry distinguishing
   the AI-driven transition from a human one.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlActivityLogStore, SqlAgentStore, SqlOpportunityStore, SqlPipelineRunStore
from app.modules.agentcore.orchestration import (
    Critic,
    InMemoryPipelineRunStore,
    Magistrate,
    Pipeline,
    PipelineConfig,
)
from app.modules.agentcore.orchestration.models import ConsolidatedOutput, SpecialistOutput
from app.modules.agents.service import Agent
from app.modules.ai import usage
from app.modules.ai.gateway import FallbackProvider
from app.modules.sales_intelligence.models import Opportunity
from app.modules.sales_intelligence.orchestration import _IdgScoutAdapter
from app.tasks import jobs
from app.tasks.jobs import run_idg_qualification_pipeline


class _RecordingSpecialist:
    """Stands in for the real Specialist: records exactly one priced model call per facet, the
    same way the real Bedrock-backed path does inside app.modules.ai.bedrock.BedrockProvider
    .generate -- so this test proves whether a usage scope is actually open around the pipeline
    run, not just that the pipeline executes."""

    def __init__(self) -> None:
        self.calls = 0

    async def work(self, bundle, facet: str) -> SpecialistOutput:
        self.calls += 1
        usage.record("anthropic.claude-3-5-haiku", "generate", input_tokens=100, output_tokens=50)
        return SpecialistOutput(facet=facet, answer=f"Answer for {facet}.", confidence=0.9, gaps="")


class _FakeSynthesizer:
    async def consolidate(self, outputs: list[SpecialistOutput]) -> ConsolidatedOutput:
        return ConsolidatedOutput(text=" ".join(o.answer for o in outputs))


def _opportunity(**overrides) -> Opportunity:
    defaults = dict(
        id="opp-1", tenant="acme", agent_id="agent-1", external_id="e1", source_key="ted",
        source_name="TED - EU Tenders", title="Risk advisory and audit services",
        buyer="Ministry of Advisory Affairs", country="France",
        stage="awaiting_review", recommendation="Review",
        deadline_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Opportunity(**defaults)


def _build_pipeline(opportunity: Opportunity, *, store, specialist=None) -> tuple[Pipeline, _RecordingSpecialist]:
    specialist = specialist or _RecordingSpecialist()
    pipeline = Pipeline(
        scout=_IdgScoutAdapter(opportunity),
        specialist=specialist,
        synthesizer=_FakeSynthesizer(),
        critic=Critic(),
        # threshold=0.0 so the deterministic grounding score always clears it -> verdict "accept".
        magistrate=Magistrate(threshold=0.0),
        store=store,
    )
    return pipeline, specialist


# --- Finding 1: usage/cost tracking -----------------------------------------------------------

async def test_run_idg_qualification_pipeline_records_cost_not_silently_dropped(caplog):
    opportunity = _opportunity()
    store = InMemoryPipelineRunStore()
    config = PipelineConfig(
        tenant=opportunity.tenant, agent_id=opportunity.agent_id, subject=opportunity.title,
        facets=["Does the notice text resolve the missing field?"], kind="idg_qualification")
    run = Pipeline.new_run(config)
    await store.add(run)
    pipeline, specialist = _build_pipeline(opportunity, store=store)

    with caplog.at_level("WARNING", logger="app.modules.ai.usage"):
        result = await run_idg_qualification_pipeline(
            tenant=opportunity.tenant, agent_id=opportunity.agent_id,
            opportunity_id=opportunity.id, run_id=run.run_id, pipeline=pipeline)

    assert specialist.calls == 1
    assert result["verdict"] == "accept"
    # The whole point of the fix: the event landed in the run's cost rather than being dropped by
    # usage.record's "no scope open" fallback.
    assert result["cost"] is not None
    assert result["cost"]["calls"] == 1
    assert result["cost"]["cost_nano_usd"] > 0
    assert not any("no scope" in r.message or "outside a scope" in r.message for r in caplog.records)

    persisted = await store.get(opportunity.tenant, opportunity.agent_id, run.run_id)
    assert persisted.cost == result["cost"]


async def test_run_idg_qualification_pipeline_without_the_fix_would_drop_the_event():
    """Negative control: calling pipeline.resume() directly (no usage scope open, as the job did
    before this fix) proves the event really is dropped rather than persisted anywhere -- the gap
    the fix closes."""
    opportunity = _opportunity()
    store = InMemoryPipelineRunStore()
    config = PipelineConfig(
        tenant=opportunity.tenant, agent_id=opportunity.agent_id, subject=opportunity.title,
        facets=["facet"], kind="idg_qualification")
    run = Pipeline.new_run(config)
    await store.add(run)
    pipeline, specialist = _build_pipeline(opportunity, store=store)

    assert usage.get_agent() is None  # sanity: no scope bleeding in from another test
    resumed = await pipeline.resume(opportunity.tenant, opportunity.agent_id, run.run_id)

    assert specialist.calls == 1
    assert resumed.cost is None  # nothing ever wrote a cost onto the run


# --- Finding 2: activity log for an autonomous stage transition ------------------------------

async def _sqlite_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_accepted_verdict_promotes_stage_and_logs_an_activity_entry():
    sessionmaker = await _sqlite_sessionmaker()
    await SqlAgentStore(sessionmaker).add(
        Agent(id="agent-1", tenant="acme", name="Sales", atype="sales_intelligence", status="ready"))

    opportunities = SqlOpportunityStore(sessionmaker)
    opportunity = await opportunities.add(_opportunity())

    run_store = SqlPipelineRunStore(sessionmaker)
    config = PipelineConfig(
        tenant=opportunity.tenant, agent_id=opportunity.agent_id, subject=opportunity.title,
        facets=["facet"], kind="idg_qualification")
    run = Pipeline.new_run(config)
    await run_store.add(run)
    pipeline, _specialist = _build_pipeline(opportunity, store=run_store)

    result = await run_idg_qualification_pipeline(
        tenant=opportunity.tenant, agent_id=opportunity.agent_id, opportunity_id=opportunity.id,
        run_id=run.run_id, pipeline=pipeline, sessionmaker=sessionmaker)

    assert result["verdict"] == "accept"

    updated = await opportunities.get(opportunity.tenant, opportunity.agent_id, opportunity.id)
    assert updated.stage == "qualified"

    logs = await SqlActivityLogStore(sessionmaker).list_for_agent(
        opportunity.tenant, opportunity.agent_id, opportunity_id=opportunity.id)
    ai_logs = [log for log in logs if log.action == "opportunity_ai_qualified"]
    assert len(ai_logs) == 1
    entry = ai_logs[0]
    assert entry.metadata["run_id"] == run.run_id
    assert entry.metadata["verdict"] == "accept"
    assert entry.metadata["from"] == "awaiting_review"
    assert entry.metadata["to"] == "qualified"
    assert entry.activity_type == "opportunity"


async def test_stage_promotion_is_skipped_without_a_sessionmaker_and_logs_nothing():
    """The eager dev/test path (pipeline passed directly, no sessionmaker) has nowhere durable to
    write the opportunity stage or the activity log, so it must not attempt either -- unchanged
    pre-existing guard, asserted here so the new logging call doesn't regress it."""
    opportunity = _opportunity()
    store = InMemoryPipelineRunStore()
    config = PipelineConfig(
        tenant=opportunity.tenant, agent_id=opportunity.agent_id, subject=opportunity.title,
        facets=["facet"], kind="idg_qualification")
    run = Pipeline.new_run(config)
    await store.add(run)
    pipeline, _specialist = _build_pipeline(opportunity, store=store)

    result = await run_idg_qualification_pipeline(
        tenant=opportunity.tenant, agent_id=opportunity.agent_id, opportunity_id=opportunity.id,
        run_id=run.run_id, pipeline=pipeline)

    assert result["verdict"] == "accept"
    # No sessionmaker -> no stage promotion, no activity-log write attempted (would raise if it
    # tried, since there is no DB here at all).


# --- Fast-tier Specialist: _build_idg_pipeline_deps ------------------------------------------

async def test_build_idg_pipeline_deps_gives_specialist_the_fast_tier_worker():
    """The Specialist makes many narrow, single-facet model calls per pipeline run, so it must
    run on the cheap/fast Bedrock tier (Settings.bedrock_model_fast) rather than the tenant's own
    configured worker tier. Synthesizer/Critic keep the capable tier -- see
    app.core.config.Settings.bedrock_model_fast and app.tasks.jobs._build_idg_pipeline_deps."""
    sessionmaker = await _sqlite_sessionmaker()
    await SqlAgentStore(sessionmaker).add(
        Agent(id="agent-1", tenant="acme", name="Sales", atype="sales_intelligence", status="ready"))
    opportunity = _opportunity()

    pipeline = await jobs._build_idg_pipeline_deps(
        sessionmaker, opportunity.tenant, opportunity.agent_id, opportunity)

    # get_provider() always wraps the configured primary with the configured fallback (see
    # tests/test_ai_gateway.py::test_get_provider_wraps_bedrock_with_stub_fallback), so the model
    # id lives on `.primary`, not directly on `.provider`.
    specialist_provider = pipeline.specialist.worker.agent.generator.provider
    assert isinstance(specialist_provider, FallbackProvider)
    assert specialist_provider.primary.model == "anthropic.claude-haiku-4-5"

    # Synthesizer keeps the real worker's own (default-tier) generator, unchanged.
    synthesizer_provider = pipeline.synthesizer.generator.provider
    assert isinstance(synthesizer_provider, FallbackProvider)
    assert synthesizer_provider.primary.model != "anthropic.claude-haiku-4-5"
