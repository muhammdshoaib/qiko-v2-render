import pytest

from app.modules.ai.gateway import StubProvider
from app.modules.chat.public import AgentNotReadyError, public_ask, studio_context_blocks
from app.modules.chat.service import ChatService
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import build_worker

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


async def _worker():
    w = build_worker(WorkerConfig(name="idg", tenant="idg"), provider=StubProvider())
    await w.ingest("iso", ISO)
    return w


async def test_public_chat_requires_ready_agent():
    with pytest.raises(AgentNotReadyError):
        await public_ask(await _worker(), ChatService(), user_email="a@x.com", question="hi", agent_ready=False)


async def test_public_chat_answers_grounded_and_records():
    w, chat = await _worker(), ChatService()
    reply = await public_ask(w, chat, user_email="a@x.com",
                             question="Describe your ISO 9001 certification.", agent_ready=True, topic="qms")
    assert reply.role == "assistant" and "ISO 9001" in reply.text
    cid = await chat.find_or_create("idg", "a@x.com", "idg")
    assert [m.role for m in await chat.history("idg", cid)] == ["user", "assistant"]


def test_studio_context_blocks_flatten():
    blocks = studio_context_blocks({"summary": "Q3 revenue up", "fileList": ["a.xlsx", "b.xlsx"], "empty": None})
    assert "Q3 revenue up" in blocks and "a.xlsx" in blocks and "b.xlsx" in blocks
    assert studio_context_blocks(None) == []


async def test_studio_context_reaches_the_answer():
    w, chat = await _worker(), ChatService()
    reply = await public_ask(w, chat, user_email="a@x.com", question="What does the data show?",
                             agent_ready=True, studio={"summary": "STUDIO_MARKER revenue grew 12%"})
    assert "STUDIO_MARKER" in reply.text  # stub echoes grounded context incl. studio blocks
