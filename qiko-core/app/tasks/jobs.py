"""The registered background tasks (the work offloaded from the request path).

Each is an async task the worker tier runs. They call the same services the API uses, so behaviour
is identical whether run eagerly (dev) or on a worker (prod).
"""
from __future__ import annotations

from app.modules.knowledge.service import KnowledgeService
from app.tasks.queue import TaskRegistry

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
    from app.modules.rfp import generation

    if packs is None:
        deps = _build_rfp_deps(sessionmaker)
        packs, reqs, answers = deps["packs"], deps["reqs"], deps["answers"]
        tree, knowledge, agents = deps["tree"], deps["knowledge"], deps["agents"]
    return await generation.run_generation(
        tenant=tenant, pack_id=pack_id, agent_id=agent_id, packs=packs, reqs=reqs,
        answers=answers, tree=tree, knowledge=knowledge, agents=agents, sessionmaker=sessionmaker)
