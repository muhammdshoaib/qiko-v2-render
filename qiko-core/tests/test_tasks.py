import pytest

from app.modules.email.sender import ConsoleEmailSender
from app.modules.knowledge.service import KnowledgeService
from app.tasks.jobs import registry
from app.tasks.queue import EagerTaskQueue, TaskError, TaskRegistry

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


def test_registered_tasks():
    assert {"ingest_document", "send_email", "generate_tender_artifacts", "run_intelligence_pipeline"} <= set(registry.names())


async def test_eager_queue_runs_ingest_and_doc_is_retrievable():
    knowledge = KnowledgeService()
    q = EagerTaskQueue(registry)
    count = await q.enqueue("ingest_document", tenant="acme", doc_id="iso", text=ISO, knowledge=knowledge)
    assert count == 1
    hits = await knowledge.retrieve("acme", "ISO 9001 certification")
    assert hits and "ISO 9001" in hits[0].text


async def test_send_email_task_delivers():
    sender = ConsoleEmailSender()
    q = EagerTaskQueue(registry)
    ok = await q.enqueue("send_email", to="a@qiko.ai", subject="Hi", body="Body", sender=sender)
    assert ok is True
    assert sender.sent[0]["to"] == "a@qiko.ai"


async def test_unknown_task_raises():
    q = EagerTaskQueue(TaskRegistry())
    with pytest.raises(TaskError):
        await q.enqueue("nope")
