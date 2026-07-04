import pytest

from app.modules.agents.service import AgentService, PlanLimitError
from app.modules.ai.gateway import StubProvider
from app.modules.billing.plans import can_create_worker, get_plan
from app.modules.chat.service import ChatService
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import build_worker

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


# --- billing gating ---
def test_plan_worker_limit_gating():
    assert can_create_worker(0, get_plan("free")) is True
    assert can_create_worker(1, get_plan("free")) is False       # free limit 1
    assert can_create_worker(4, get_plan("pro")) is True         # pro limit 5
    assert can_create_worker(999, get_plan("enterprise")) is True  # unlimited


# --- agent lifecycle + gating ---
def test_agent_lifecycle_and_plan_limit():
    svc = AgentService()
    free = get_plan("free")
    a = svc.create("acme", "IDG worker", free)
    assert a.status == "training"
    svc.mark_ready("acme", a.id)
    assert svc.list("acme")[0].status == "ready"
    with pytest.raises(PlanLimitError):
        svc.create("acme", "second", free)  # free allows only 1
    # a different tenant is unaffected
    assert svc.create("beta", "theirs", free).tenant == "beta"


# --- chat history + agentic answer ---
async def test_chat_records_and_answers():
    worker = build_worker(WorkerConfig(name="idg", tenant="idg"), provider=StubProvider())
    await worker.ingest("iso", ISO)
    chat = ChatService()
    reply = await chat.ask(worker, "conv-1", "Describe your ISO 9001 certification.", topic="qms")
    assert reply.role == "assistant" and "ISO 9001" in reply.text
    hist = await chat.history("idg", "conv-1")
    assert [m.role for m in hist] == ["user", "assistant"]
