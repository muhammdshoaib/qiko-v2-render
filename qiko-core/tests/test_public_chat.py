import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.chat.public import AgentNotReadyError, public_ask, studio_context_blocks
from app.modules.chat.service import ChatService
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import build_worker

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


class _Provider:
    def generate(self, prompt, **_kwargs):
        return LLMResponse(text=prompt, model="test", stub=False)


async def _worker():
    w = build_worker(WorkerConfig(name="idg", tenant="idg"), provider=_Provider())
    await w.ingest("iso", ISO)
    return w


async def _ready() -> None:
    return None


async def _not_ready() -> None:
    raise AgentNotReadyError("not ready")


async def test_public_chat_requires_ready_agent():
    with pytest.raises(AgentNotReadyError):
        await public_ask(
            await _worker(), ChatService(), agent_id="worker-1",
            user_email="a@invalid", question="hi", recheck_worker=_not_ready)


async def test_public_chat_answers_grounded_and_records():
    w, chat = await _worker(), ChatService()
    reply = await public_ask(w, chat, agent_id="worker-1", user_email="a@invalid",
                             question="Describe your ISO 9001 certification.", recheck_worker=_ready, topic="qms")
    assert reply.role == "assistant" and "ISO 9001" in reply.text
    # Recorded under the real agent id (worker-1), not worker.name ("idg") -- otherwise nothing
    # that looks up "this worker's conversations" by its real id (e.g. the CRM pipeline) would
    # ever find public-embed chats.
    cid = await chat.find_or_create("idg", "a@invalid", "worker-1")
    assert [m.role for m in await chat.history("idg", cid)] == ["user", "assistant"]


async def test_public_chat_conversation_keyed_by_real_agent_id_not_display_name():
    """Regression: public_ask used to key the conversation by worker.name (a display name like
    "IDG - Sales Intelligence"), not the real agent id -- so nothing that looks a worker's
    conversations up by id (e.g. the CRM pipeline) could ever find public-embed chats."""
    w, chat = await _worker(), ChatService()  # WorkerConfig(name="idg", ...) -- name != agent id on purpose
    await public_ask(w, chat, agent_id="agent-xyz", user_email="a@invalid", question="hi", recheck_worker=_ready)
    by_real_id = await chat.list_for_agent("idg", "agent-xyz")
    by_display_name = await chat.list_for_agent("idg", "idg")
    assert len(by_real_id) == 1
    assert len(by_display_name) == 0


def test_studio_context_blocks_flatten():
    blocks = studio_context_blocks({"summary": "Q3 revenue up", "fileList": ["a.xlsx", "b.xlsx"], "empty": None})
    assert "Q3 revenue up" in blocks and "a.xlsx" in blocks and "b.xlsx" in blocks
    assert studio_context_blocks(None) == []


async def test_studio_context_reaches_the_answer():
    w, chat = await _worker(), ChatService()
    reply = await public_ask(w, chat, agent_id="worker-1", user_email="a@invalid", question="What does the data show?",
                             recheck_worker=_ready, studio={"summary": "STUDIO_MARKER revenue grew 12%"})
    assert "STUDIO_MARKER" in reply.text  # stub echoes grounded context incl. studio blocks
