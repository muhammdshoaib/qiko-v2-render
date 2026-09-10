"""The registered background tasks (the work offloaded from the request path).

Each is an async task the worker tier runs. They call the same services the API uses, so behaviour
is identical whether run eagerly (dev) or on a worker (prod).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import uuid

from app.core.tenancy import reset_tenant, set_tenant
from app.modules.ai import usage
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.intelligence.documents import DocumentService
from app.modules.knowledge.service import KnowledgeService
from app.tasks.queue import TaskRegistry

logger = logging.getLogger(__name__)
registry = TaskRegistry()

# A process-wide knowledge service; in prod this is constructed with the DB-backed vector store.
_knowledge = KnowledgeService()

# The audit store the eager task backend uses, wired in main.py. Same shape as _knowledge above.
#
# Only the EAGER backend reaches this: on a worker the ctx wrapper passes its own store, built on the
# maintenance connection. So in production the API never holds a store that can UPDATE audit_events, and
# in dev and tests, where the eager backend runs the job inline, the in-memory store has no privilege
# boundary to violate.
_audit_store: object | None = None


@registry.register("ingest_document")
async def ingest_document(*, tenant: str, doc_id: str, text: str,
                          agent_id: str | None = None,
                          knowledge: KnowledgeService | None = None) -> int:
    """Chunk + embed + store a document. Heavy, so it runs off the request path."""
    svc = knowledge or _knowledge
    return await svc.ingest(tenant, doc_id, text, agent_id=agent_id)


@registry.register("process_uploaded_document")
async def process_uploaded_document(
    *,
    tenant: str,
    agent_id: str,
    doc_id: str,
    storage_key: str,
    filename: str,
    content_type: str,
    actor: str,
    document_service: DocumentService | None = None,
    sessionmaker=None,
) -> None:
    """Parse, chunk, embed and emit a signal for an uploaded document.

    The API passes a built DocumentService when running eagerly (dev/tests); in production the
    arq worker passes a sessionmaker and the services are built here so only serialisable ids
    cross Redis.
    """
    if document_service is None:
        if sessionmaker is None:
            raise ValueError("process_uploaded_document requires sessionmaker or document_service")
        from app.core.config import get_settings
        from app.db.stores import SqlDocumentStore, SqlSignalStore, SqlVectorStore
        from app.modules.intelligence.documents import DocumentService as _DocumentService
        from app.modules.storage.backend import InMemoryStorage, S3Storage

        settings = get_settings()
        storage = InMemoryStorage()
        if settings.s3_bucket:
            storage = S3Storage(bucket=settings.s3_bucket)
        document_service = _DocumentService(
            document_store=SqlDocumentStore(sessionmaker),
            knowledge=KnowledgeService(store=SqlVectorStore(sessionmaker)),
            signal_store=SqlSignalStore(sessionmaker),
            storage=storage,
        )
    await document_service.process(
        tenant=tenant,
        agent_id=agent_id,
        doc_id=doc_id,
        storage_key=storage_key,
        filename=filename,
        actor=actor,
    )


@registry.register("send_email")
async def send_email(*, to: str, subject: str, body: str, html: str | None = None, sender=None) -> bool:
    """Send a transactional email (delegated to the email sender; SCRUM-25)."""
    from app.modules.email.sender import get_email_sender

    return (sender or get_email_sender()).send(to=to, subject=subject, body=body, html=html)


def _usage_store(sessionmaker):
    """The durable usage store, or None when no sessionmaker is available (dev/tests run eagerly
    with in-memory stores and simply keep the events in the scope)."""
    if sessionmaker is None:
        return None
    from app.db.stores import SqlUsageStore

    return SqlUsageStore(sessionmaker)


def _build_rfp_deps(sessionmaker):
    """Assemble the DB-backed RFP stores + knowledge/agents from a sessionmaker, mirroring the
    lifespan wiring in app.main -- so the background job reads/writes the same source of truth as
    the API when running on the arq worker tier (no Request available)."""
    from app.db.stores import (
        SqlAgentStore,
        SqlPackAnswerStore,
        SqlPackQuestionStore,
        SqlPackSectionStore,
        SqlRequirementStore,
        SqlRfpPackStore,
        SqlVectorStore,
    )
    from app.modules.agents.service import AgentService
    from app.modules.rfp.service import PackAnswerService, RequirementService, RfpPackService
    from app.modules.rfp.tree import PackTreeService

    return {
        "packs": RfpPackService(store=SqlRfpPackStore(sessionmaker)),
        "reqs": RequirementService(store=SqlRequirementStore(sessionmaker)),
        "answers": PackAnswerService(store=SqlPackAnswerStore(sessionmaker)),
        "tree": PackTreeService(sections=SqlPackSectionStore(sessionmaker),
                                questions=SqlPackQuestionStore(sessionmaker)),
        "knowledge": KnowledgeService(store=SqlVectorStore(sessionmaker)),
        "agents": AgentService(store=SqlAgentStore(sessionmaker)),
    }


@registry.register("generate_tender_artifacts")
async def generate_tender_artifacts(*, tenant: str, pack_id: str, agent_id: str | None = None,
                                    packs=None, reqs=None, answers=None, tree=None,
                                    knowledge=None, agents=None, sessionmaker=None) -> dict:
    """Background job: on tender upload, generate + persist ALL artifacts (requirements, sections,
    brief, compliance, per-section drafts) with a pollable per-artifact gen_status.

    Callers may inject already-built services (the API's eager/inline path passes app.state's
    stores directly, so an in-memory dev/test run reaches the same data); otherwise the services
    are built from `sessionmaker` (the arq worker tier passes ctx["sessionmaker"])."""
    from app.modules.ai import usage
    from app.modules.rfp import generation

    if packs is None:
        deps = _build_rfp_deps(sessionmaker)
        packs, reqs, answers = deps["packs"], deps["reqs"], deps["answers"]
        tree, knowledge, agents = deps["tree"], deps["knowledge"], deps["agents"]
    # This job runs on the arq worker tier with no request around it, so nothing binds the tenant or
    # opens a usage scope. Without this, the largest token consumer in the platform (extraction,
    # brief, compliance and one draft per section) recorded no spend at all.
    tenant_token = set_tenant(tenant)
    try:
        with usage.scope() as events:
            try:
                return await generation.run_generation(
                    tenant=tenant, pack_id=pack_id, agent_id=agent_id, packs=packs, reqs=reqs,
                    answers=answers, tree=tree, knowledge=knowledge, agents=agents,
                    sessionmaker=sessionmaker)
            finally:
                # Flushed even when generation fails: the tokens were still spent.
                await usage.flush(_usage_store(sessionmaker), events)
    finally:
        reset_tenant(tenant_token)


def _fast_tier_worker(worker):
    """A Specialist-only Worker on the cheap/fast Bedrock tier (Settings.bedrock_model_fast).

    Same config/knowledge/cost_guard as the tenant's own resolved `worker`, but its own Generator
    (a different AgentCore instance), so this never changes the tier the tenant's OWN chat uses
    via `worker.agent.generator` -- only the copy handed to Specialist is fast-tier. The
    Specialist makes many narrow, single-facet calls per pipeline run; Synthesizer/Critic keep
    the capable tier (see Settings.bedrock_model_fast).

    `system_prompt` and `reference_scoped` are carried over from the real worker's generator
    (see app.core.deps.assemble_worker) rather than left at Generator's dataclass defaults: they
    hold the tenant's own Train-wizard-synthesized persona and whether this job is restricted to
    one reference document. Only `provider` (and therefore the model tier) should differ between
    this Generator and the real worker's."""
    from app.core.config import get_settings
    from app.modules.agentcore.generator import Generator
    from app.modules.agentcore.runtime import AgentCore
    from app.modules.ai.gateway import get_provider
    from app.modules.workers.worker import Worker

    return Worker(
        config=worker.config, knowledge=worker.knowledge,
        agent=AgentCore(
            generator=Generator(
                provider=get_provider(model=get_settings().bedrock_model_fast),
                system_prompt=worker.agent.generator.system_prompt,
                reference_scoped=worker.agent.generator.reference_scoped),
            verified=worker.agent.verified, threshold=worker.agent.threshold),
        cost_guard=worker.cost_guard)


async def _build_pipeline_deps(sessionmaker, tenant: str, agent_id: str):
    """Build a Postgres-backed Pipeline for the arq worker tier, mirroring the in-memory wiring
    in app.main."""
    from app.core.deps import resolve_available_worker
    from app.db.stores import (
        SqlAgentStore,
        SqlDocumentStore,
        SqlPipelineRunStore,
        SqlSignalStore,
        SqlVectorStore,
    )
    from app.modules.agents.service import AgentService
    from app.modules.intelligence.orchestration import (
        Critic,
        Magistrate,
        Pipeline,
        Scout,
        Specialist,
        Synthesizer,
    )
    from app.modules.knowledge.service import KnowledgeService

    knowledge = KnowledgeService(store=SqlVectorStore(sessionmaker))
    agents = AgentService(store=SqlAgentStore(sessionmaker))
    worker, _ = await resolve_available_worker(
        sessionmaker=sessionmaker, agents=agents, knowledge=knowledge,
        tenant=tenant, agent_id=agent_id)
    return Pipeline(
        scout=Scout(
            knowledge,
            signal_store=SqlSignalStore(sessionmaker),
            document_store=SqlDocumentStore(sessionmaker),
        ),
        specialist=Specialist(_fast_tier_worker(worker)),
        synthesizer=Synthesizer(worker.agent.generator),
        critic=Critic(),
        magistrate=Magistrate(threshold=worker.agent.threshold),
        store=SqlPipelineRunStore(sessionmaker),
    )


@registry.register("run_intelligence_pipeline")
async def run_intelligence_pipeline(
    *,
    tenant: str,
    agent_id: str,
    run_id: str,
    pipeline: object | None = None,
    sessionmaker=None,
) -> dict:
    """Background job: execute or resume an intelligence pipeline run.

    The eager dev/test path passes a pre-built `Pipeline`; the arq worker tier passes only
    `sessionmaker` and the ids, and this function rebuilds the Pipeline from the worker's own
    DB connection."""
    run = None
    events: list = []
    agent_token = usage.set_agent(agent_id)
    tenant_token = set_tenant(tenant)
    try:
        with usage.scope() as events:
            if pipeline is not None:
                run = await pipeline.resume(tenant, agent_id, run_id)
            else:
                if sessionmaker is None:
                    raise ValueError("run_intelligence_pipeline requires sessionmaker or pipeline")
                pipeline = await _build_pipeline_deps(sessionmaker, tenant, agent_id)
                run = await pipeline.resume(tenant, agent_id, run_id)
    finally:
        if run is not None and pipeline is not None:
            run.cost = dataclasses.asdict(usage.accumulate(events))
            await pipeline.store.update(run)
        await usage.flush(_usage_store(sessionmaker), events)
        usage.reset_agent(agent_token)
        reset_tenant(tenant_token)
    if run is None:
        raise ValueError(f"pipeline run {run_id} not found")
    return {"run_id": run.run_id, "verdict": run.verdict, "status": run.status, "cost": run.cost}


async def _build_idg_pipeline_deps(sessionmaker, tenant: str, agent_id: str, opportunity):
    """Build a Postgres-backed Pipeline for IDG qualification, mirroring _build_pipeline_deps.

    Takes the already-fetched Opportunity (the caller needs it anyway, to build this) so the
    Scout adapter can close over it: IdgScout.gather() takes a single Opportunity, not the
    (tenant, agent_id, subject) triple the generic Pipeline calls its scout with -- see
    app.modules.sales_intelligence.orchestration._IdgScoutAdapter.
    """
    from app.core.deps import resolve_available_worker
    from app.db.stores import SqlAgentStore, SqlPipelineRunStore, SqlVectorStore
    from app.modules.agentcore.orchestration import Critic, Magistrate, Pipeline, Synthesizer
    from app.modules.agents.service import AgentService
    from app.modules.intelligence.orchestration import Specialist
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.sales_intelligence.orchestration import _IdgScoutAdapter

    knowledge = KnowledgeService(store=SqlVectorStore(sessionmaker))
    agents = AgentService(store=SqlAgentStore(sessionmaker))
    worker, _ = await resolve_available_worker(
        sessionmaker=sessionmaker, agents=agents, knowledge=knowledge,
        tenant=tenant, agent_id=agent_id)
    return Pipeline(
        scout=_IdgScoutAdapter(opportunity),
        specialist=Specialist(_fast_tier_worker(worker)),
        synthesizer=Synthesizer(worker.agent.generator),
        critic=Critic(),
        magistrate=Magistrate(threshold=worker.agent.threshold),
        store=SqlPipelineRunStore(sessionmaker),
    )


async def _record_idg_stage_promotion(sessionmaker, opportunity, run) -> None:
    """Durable audit trail for an autonomous stage transition: the IDG qualification pipeline
    accepting a notice moves its stage from awaiting_review to qualified with no human in the
    loop, so this is the record that distinguishes an AI-driven qualification from a human one
    (mirrors OpportunityService._log()'s ActivityLog shape -- see
    app.modules.sales_intelligence.service.OpportunityService._log and .models.ActivityLog).

    Reached directly via SqlActivityLogStore rather than through a full OpportunityService: this
    job already builds the Sql*Store objects it needs inline (see _build_idg_pipeline_deps and
    the SqlOpportunityStore use above), and OpportunityService itself needs connectors/qualifier/
    notifier collaborators this job has no use for, so constructing one just to reach `_log()`
    would be a bigger dependency than the write it performs."""
    from app.db.stores import SqlActivityLogStore
    from app.modules.sales_intelligence.models import ActivityLog

    await SqlActivityLogStore(sessionmaker).add(ActivityLog(
        id=uuid.uuid4().hex[:12], tenant=opportunity.tenant, agent_id=opportunity.agent_id,
        action="opportunity_ai_qualified",
        detail=f"AI qualification pipeline run {run.run_id} accepted this opportunity and "
               "advanced it to qualified.",
        tone="success", opportunity_id=opportunity.id,
        metadata={"run_id": run.run_id, "verdict": run.verdict,
                  "from": "awaiting_review", "to": "qualified"},
    ))


@registry.register("run_idg_qualification_pipeline")
async def run_idg_qualification_pipeline(
    *,
    tenant: str,
    agent_id: str,
    opportunity_id: str,
    run_id: str,
    pipeline: object | None = None,
    sessionmaker=None,
) -> dict:
    """Background job: execute an IDG qualification pipeline run, then apply its verdict to the
    opportunity's stage. Mirrors run_intelligence_pipeline's eager-vs-arq dual path: the eager
    dev/test path may pass a pre-built `Pipeline` directly; the arq worker tier passes only
    `sessionmaker` and the ids, and this function fetches the Opportunity and rebuilds the
    Pipeline (via _build_idg_pipeline_deps) from the worker's own DB connection.

    Also mirrors run_intelligence_pipeline's usage-tracking wrapping (set_agent/set_tenant before
    execution, usage.scope() around the pipeline.resume() call, the accumulated cost written onto
    the run and flushed to the durable usage store in a `finally`): without it, every Specialist/
    Synthesizer model call this pipeline makes runs with no usage scope open, so usage.record()
    hits its "no scope open" fallback and the event is dropped rather than persisted -- this
    pipeline's real AI spend would otherwise be invisible to cost accounting and PipelineRun.cost
    would stay unset.

    An "accept" verdict promotes the opportunity's stage from awaiting_review to qualified with no
    human in the loop; see _record_idg_stage_promotion for the activity-log entry that records it.
    """
    run = None
    events: list = []
    agent_token = usage.set_agent(agent_id)
    tenant_token = set_tenant(tenant)
    try:
        with usage.scope() as events:
            if pipeline is None:
                if sessionmaker is None:
                    raise ValueError("run_idg_qualification_pipeline requires sessionmaker or pipeline")
                from app.db.stores import SqlOpportunityStore

                opportunity = await SqlOpportunityStore(sessionmaker).get(tenant, agent_id, opportunity_id)
                if opportunity is None:
                    raise ValueError(f"opportunity {opportunity_id} not found")
                pipeline = await _build_idg_pipeline_deps(sessionmaker, tenant, agent_id, opportunity)

            run = await pipeline.resume(tenant, agent_id, run_id)
    finally:
        if run is not None and pipeline is not None:
            run.cost = dataclasses.asdict(usage.accumulate(events))
            await pipeline.store.update(run)
        await usage.flush(_usage_store(sessionmaker), events)
        usage.reset_agent(agent_token)
        reset_tenant(tenant_token)
    if run is None:
        raise ValueError(f"pipeline run {run_id} not found")

    if run.verdict == "accept" and sessionmaker is not None:
        from app.db.stores import SqlOpportunityStore

        opportunities = SqlOpportunityStore(sessionmaker)
        opportunity = await opportunities.get(tenant, agent_id, opportunity_id)
        if opportunity is not None and opportunity.stage == "awaiting_review":
            opportunity.stage = "qualified"
            await opportunities.update(opportunity)
            await _record_idg_stage_promotion(sessionmaker, opportunity, run)
    return {"run_id": run.run_id, "verdict": run.verdict, "status": run.status, "cost": run.cost}


async def apply_audit_retention(store) -> dict:
    """Enforce the audit trail's retention policy.

    Runs as a job rather than on request, and records its own outcome into the trail it just pruned.
    That is deliberate: "the retention job ran, deleted N events past the cutoff and cleared M
    addresses" is the artefact an auditor asks for when they check that a stated policy is actually
    implemented, and a policy nobody can show running is a paragraph rather than a control.

    The counts are the evidence, so a run that deletes nothing still writes a row.
    """
    result = await store.apply_retention()
    logger.info("audit retention applied", extra={"source": "tasks.audit", **result})
    await audit.record(store, audit.AuditEvent(
        action=audit_actions.RETENTION_APPLIED, target_id="audit_events",
        actor_type=audit.JOB, actor_id="arq:apply_audit_retention",
        actor_label="scheduled retention",
        changes=audit.diff(audit_actions.RETENTION_APPLIED, {}, {
            "events_deleted": result["events_deleted"],
            "addresses_cleared": result["addresses_cleared"]}),
        metadata=result))
    return result


async def export_audit_archive(audit_store, archive_store, storage, *, day=None) -> dict:
    """Write one day of the audit trail to write-once storage, with a chained digest.

    Yesterday by default, not today: exporting a day still in progress would produce an object that is
    incomplete the moment it is written, and a digest that legitimately changes on re-export, which
    destroys the only property the digest has.

    A day with no events is still exported. An absent object is indistinguishable from a deleted one, and
    deleting a whole day is the easier attack than editing a row inside one; the chain is what makes a
    missing day visible, and it only works if every day is a link.
    """
    from datetime import date, timedelta

    from app.modules.audit.archive import build_day_export

    target = day or (date.today() - timedelta(days=1))
    previous = await archive_store.latest()
    rows = await audit_store.rows_for_day(target)
    export = build_day_export(rows, target, previous_digest=previous["digest"] if previous else None)

    # The manifest goes in the SAME object as the rows, so a retrieval cannot get one without the other.
    payload = (json.dumps({"manifest": export.manifest()}, sort_keys=True) + "\n").encode() + export.body
    storage.put("audit-archive", export.key, payload, content_type="application/x-ndjson")
    await archive_store.record(
        day=target.isoformat(), row_count=export.row_count, digest=export.digest,
        previous_digest=export.previous_digest, object_key=export.key)

    logger.info("audit archive exported", extra={
        "source": "tasks.audit", "day": target.isoformat(), "rows": export.row_count,
        "digest": export.digest, "key": export.key})
    return {"day": target.isoformat(), "row_count": export.row_count, "digest": export.digest,
            "object_key": export.key}


@registry.register("erase_audit_subject")
async def erase_audit_subject(*, identifier: str, pseudonym: str, request_ref: str,
                              actor_email: str, store=None) -> int:
    """Pseudonymise a subject throughout the audit trail.

    ON THE WORKER, not in the request, and that is the whole point. Erasure is the only operation that
    UPDATEs audit_events, so leaving it in the API meant the API process had to hold a connection able to
    rewrite history. Every other write path went through a store that could not, which made the boundary
    "one handler away from useless". Here the privileged connection exists only in the worker, where no
    request can reach it.

    The cost is that the endpoint returns "accepted" instead of a row count. For a request that takes days
    to fulfil, seconds of asynchrony is not a real loss, and the count still appears in the trail.

    Idempotent: a re-run pseudonymises whatever is left, which is zero after a successful first run. That
    matters because a failed job is retried, and a retry must not produce a second row claiming a second
    erasure.
    """
    audit_store = store or _audit_store
    if audit_store is None:
        raise ValueError("erase_audit_subject requires an audit store")

    def build_record(affected: int) -> dict:
        # Built inside the store's transaction, so the erasure cannot land without its record and a
        # failed erasure cannot leave a row claiming one. The pseudonym IS the target: putting the
        # address there would undo the erasure in the very row that records it.
        return audit.build_row(audit.AuditEvent(
            action=audit_actions.SUBJECT_ERASED, target_id=pseudonym, tenant_id=None,
            actor_type=audit.PLATFORM_ADMIN, actor_id=actor_email, actor_label=actor_email,
            changes=audit.diff(audit_actions.SUBJECT_ERASED, {},
                               {"rows_pseudonymised": affected, "request_ref": request_ref}),
            metadata={"scope": ["audit_events"], "executed_by": "worker"}))

    rows = await audit_store.pseudonymise_subject(identifier, pseudonym, audit_row=build_record)
    # Logged at INFO with the reference but NOT the identifier: the job argument had to carry the address
    # to do the work, and the log is the one place it would outlive the erasure.
    logger.info("audit subject erased", extra={
        "source": "tasks.audit", "request_ref": request_ref, "rows": rows,
        "pseudonym": pseudonym})
    return rows


def _slack_worker_from_state():
    """Build a DigestWorker from the live FastAPI app state (the eager dev/test path)."""
    from app.main import app
    from app.modules.channels.digest_scheduler import DigestWorker

    return DigestWorker(
        message_store=app.state.slack_messages,
        installation_store=app.state.slack_oauth.store,
        cost_guard=getattr(app.state, "cost_guard", None),
        usage_store=getattr(app.state, "ai_usage", None),
        agent_store=app.state.agents,
    )


def _slack_worker_from_sessionmaker(sessionmaker, *, sync_sessionmaker=None):
    """Build a DigestWorker for the arq worker tier.

    The installation store is built HERE from the worker's own sessionmaker rather than being
    passed in: an earlier version left it None, so the job resolved no bot token, raised after the
    model had already been billed, and arq retried it three times.
    """
    from app.db.stores import SqlAgentStore, SqlSlackChannelStore, SqlCostCapStore, SqlUsageStore
    from app.modules.agents.service import AgentService
    from app.modules.ai.caps import CostGuard
    from app.modules.ai.gateway import get_provider

    from app.modules.channels.digest_scheduler import DigestWorker

    installation_store = None
    if sync_sessionmaker is not None:
        from app.db.sync_stores import SqlSlackInstallationStore

        installation_store = SqlSlackInstallationStore(sync_sessionmaker)

    usage_store = SqlUsageStore(sessionmaker)
    return DigestWorker(
        message_store=SqlSlackChannelStore(sessionmaker),
        installation_store=installation_store,
        provider=get_provider(),
        cost_guard=CostGuard(caps=SqlCostCapStore(sessionmaker), usage=usage_store),
        usage_store=usage_store,
        agent_store=AgentService(store=SqlAgentStore(sessionmaker)),
    )


@registry.register("generate_slack_digest")
async def generate_slack_digest(*, tenant: str, agent_id: str | None = None, team_id: str,
                                channel_id: str, enterprise_id: str | None = None,
                                sessionmaker=None, sync_sessionmaker=None) -> dict:
    """Background job: generate and post a Slack heads-up digest after inactivity."""
    worker = (_slack_worker_from_state() if sessionmaker is None
              else _slack_worker_from_sessionmaker(sessionmaker,
                                                   sync_sessionmaker=sync_sessionmaker))
    return await worker.run(tenant=tenant, agent_id=agent_id, team_id=team_id,
                            channel_id=channel_id, enterprise_id=enterprise_id)


async def purge_slack_messages(store, *, retention_days: int) -> dict:
    """Retention for captured Slack text.

    Runs daily. Without it the table keeps third-party personal data for every channel whose
    digest never posted, which is exactly the case the rest of this feature fails closed into.
    """
    from datetime import timedelta
    from app.db.stores import SqlVectorStore
    from app.modules.knowledge.service import KnowledgeService

    if getattr(store, "knowledge", None) is None and getattr(store, "sessionmaker", None) is not None:
        store.knowledge = KnowledgeService(store=SqlVectorStore(store.sessionmaker))

    deleted = await store.purge_older_than(timedelta(days=retention_days))
    logger.info("slack messages purged", extra={
        "source": "tasks.channels", "deleted": deleted, "retention_days": retention_days})
    return {"deleted": deleted, "retention_days": retention_days}
