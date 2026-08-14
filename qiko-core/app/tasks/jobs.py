"""The registered background tasks (the work offloaded from the request path).

Each is an async task the worker tier runs. They call the same services the API uses, so behaviour
is identical whether run eagerly (dev) or on a worker (prod).
"""
from __future__ import annotations

import json
import logging

from app.core.tenancy import reset_tenant, set_tenant
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
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
async def ingest_document(*, tenant: str, doc_id: str, text: str, knowledge: KnowledgeService | None = None) -> int:
    """Chunk + embed + store a document. Heavy, so it runs off the request path."""
    svc = knowledge or _knowledge
    return await svc.ingest(tenant, doc_id, text)


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
    )


def _slack_worker_from_sessionmaker(sessionmaker, *, sync_sessionmaker=None):
    """Build a DigestWorker for the arq worker tier.

    The installation store is built HERE from the worker's own sessionmaker rather than being
    passed in: an earlier version left it None, so the job resolved no bot token, raised after the
    model had already been billed, and arq retried it three times.
    """
    from app.db.stores import SqlSlackChannelStore, SqlCostCapStore, SqlUsageStore
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
    )


@registry.register("generate_slack_digest")
async def generate_slack_digest(*, tenant: str, team_id: str, channel_id: str,
                                enterprise_id: str | None = None,
                                sessionmaker=None, sync_sessionmaker=None) -> dict:
    """Background job: generate and post a Slack heads-up digest after inactivity."""
    worker = (_slack_worker_from_state() if sessionmaker is None
              else _slack_worker_from_sessionmaker(sessionmaker,
                                                   sync_sessionmaker=sync_sessionmaker))
    return await worker.run(tenant=tenant, team_id=team_id, channel_id=channel_id,
                            enterprise_id=enterprise_id)


async def purge_slack_messages(store, *, retention_days: int) -> dict:
    """Retention for captured Slack text.

    Runs daily. Without it the table keeps third-party personal data for every channel whose
    digest never posted, which is exactly the case the rest of this feature fails closed into.
    """
    from datetime import timedelta

    deleted = await store.purge_older_than(timedelta(days=retention_days))
    logger.info("slack messages purged", extra={
        "source": "tasks.channels", "deleted": deleted, "retention_days": retention_days})
    return {"deleted": deleted, "retention_days": retention_days}
