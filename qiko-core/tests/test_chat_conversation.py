from app.modules.ai.gateway import StubProvider
from app.modules.chat.service import ChatService
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import build_worker

from tests.helpers import auth_cookies


async def test_find_or_create_is_deterministic_per_user_agent():
    chat = ChatService()
    a = await chat.find_or_create("t", "user-1", "agent-9")
    b = await chat.find_or_create("t", "user-1", "agent-9")
    c = await chat.find_or_create("t", "user-2", "agent-9")
    assert a == b       # same user+agent resumes the same conversation
    assert a != c       # different user -> different conversation


async def test_history_window_limits_and_clear():
    chat = ChatService()
    cid = await chat.find_or_create("t", "u", "a")
    for i in range(25):
        await chat.post("t", cid, "user", f"msg {i}")
    recent = await chat.history("t", cid, limit=20)
    assert len(recent) == 20
    assert recent[-1].text == "msg 24" and recent[0].text == "msg 5"  # last 20
    await chat.clear("t", cid)
    assert await chat.history("t", cid) == []


async def test_history_is_tenant_scoped():
    chat = ChatService()
    cid = await chat.find_or_create("acme", "u", "a")
    await chat.post("acme", cid, "user", "secret")
    assert await chat.history("beta", cid) == []  # other tenant sees nothing


async def test_ask_with_a_never_created_conversation_id_still_attributes_the_real_agent_id():
    """Regression: chat.ask() used to call self.post() -> store.append() -> store.ensure()
    with NO agent_id, so a caller that mints its own client-side conversation id and calls
    /chat/ask directly (the dashboard's own test-chat does exactly this) got it silently
    recorded under a generic "public" agent -- meaning it could never be found by anything
    that looks a worker's own conversations up by its real agent id (the CRM pipeline)."""
    chat = ChatService()
    worker = build_worker(WorkerConfig(name="Pre Sales Writer Worker", tenant="acme"), provider=StubProvider())
    await chat.ask(worker, "client-minted-conv-id", "hello", agent_id="agent-real-id")
    assert len(await chat.list_for_agent("acme", "agent-real-id")) == 1
    assert len(await chat.list_for_agent("acme", "public")) == 0


def test_ask_endpoint_attributes_conversation_to_the_real_agent_id(client):
    import asyncio

    c = auth_cookies("chatco", "owner")
    r = client.post("/api/v1/chat/ask", cookies=c,
                    json={"conversation_id": "test-123", "agent_id": "agent-dash", "question": "hi"})
    assert r.status_code == 200
    found = asyncio.run(client.app.state.chat.list_for_agent("chatco", "agent-dash"))
    assert len(found) == 1
