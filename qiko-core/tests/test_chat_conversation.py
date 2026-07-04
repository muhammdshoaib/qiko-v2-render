from app.modules.chat.service import ChatService


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
