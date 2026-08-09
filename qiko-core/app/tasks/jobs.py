"""The registered background tasks (the work offloaded from the request path).

Each is an async task the worker tier runs. They call the same services the API uses, so behaviour
is identical whether run eagerly (dev) or on a worker (prod).
"""
from __future__ import annotations

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
