"""Postgres-backed chat history over SqlChatStore (exercised on aiosqlite)."""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import pytest

from app.db.base import Base
from app.db.models import Agent as AgentRow
from app.db.models import Tenant
from app.db.stores import SqlChatStore
from app.modules.chat.service import ChatService, ConversationScopeError


async def _chat(path) -> ChatService:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ChatService(store=SqlChatStore(async_sessionmaker(engine, expire_on_commit=False)))


async def test_db_backed_chat_history(tmp_path):
    chat = await _chat(tmp_path / "c.db")
    cid = await chat.find_or_create("acme", "u1", "ag1")
    await chat.post("acme", cid, "user", "hi")
    await chat.post("acme", cid, "assistant", "hello")
    hist = await chat.history("acme", cid)
    assert [(m.role, m.text) for m in hist] == [("user", "hi"), ("assistant", "hello")]
    # tenant isolation
    assert await chat.history("beta", cid) == []
    await chat.clear("acme", cid)
    assert await chat.history("acme", cid) == []


async def test_guarded_exchange_is_atomic_and_conversation_is_agent_scoped(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'guarded.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session, session.begin():
        session.add(Tenant(id="acme", name="Acme"))
        session.add(AgentRow(id="a1", tenant_id="acme", name="A1", enabled=True))
        session.add(AgentRow(id="a2", tenant_id="acme", name="A2", enabled=True))
    store = SqlChatStore(sm)

    async def available() -> None:
        return None

    await store.append_exchange_for_enabled_agent(
        "acme", "shared", user_id="u1", agent_id="a1",
        user_text="question", assistant_text="answer", recheck_worker=available)
    history = await store.history("acme", "shared")
    assert [(message.role, message.text) for message in history] == [
        ("user", "question"), ("assistant", "answer")
    ]
    with pytest.raises(ConversationScopeError):
        await store.ensure_for_enabled_agent(
            "acme", "shared", user_id="u1", agent_id="a2",
            recheck_worker=available)
    await engine.dispose()
