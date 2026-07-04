"""Postgres-backed chat history over SqlChatStore (exercised on aiosqlite)."""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlChatStore
from app.modules.chat.service import ChatService


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
