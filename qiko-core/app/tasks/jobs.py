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
async def send_email(*, to: str, subject: str, body: str, sender=None) -> bool:
    """Send a transactional email (delegated to the email sender; SCRUM-25)."""
    from app.modules.email.sender import get_email_sender

    return (sender or get_email_sender()).send(to=to, subject=subject, body=body)
