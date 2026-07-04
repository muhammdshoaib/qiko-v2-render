import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlUserStore, SqlVectorStore, SqlVerifiedStore
from app.modules.identity.rbac import Role
from app.modules.identity.security import hash_password
from app.modules.identity.store import User
from app.modules.knowledge.models import Passage


async def _sessionmaker(path: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "qiko.db")


async def test_user_store_crud_and_revocation(db_path):
    sm, engine = await _sessionmaker(db_path)
    store = SqlUserStore(sm)
    await store.add(User(id="u1", email="Owner@Qiko.ai", password_hash=hash_password("pw"),
                         tenant="acme", role=Role.owner))
    got = await store.get_by_email("owner@qiko.ai")
    assert got and got.id == "u1" and got.role is Role.owner
    assert (await store.get_by_id("u1")).tenant == "acme"
    await store.set_sid("u1", "sid-123")
    assert (await store.get_by_id("u1")).current_sid == "sid-123"
    await engine.dispose()


async def test_persists_across_restart(db_path):
    sm1, e1 = await _sessionmaker(db_path)
    await SqlVerifiedStore(sm1).add("acme", "qms", "ISO 9001 held")
    await e1.dispose()  # simulate redeploy/restart
    sm2 = async_sessionmaker(create_async_engine(f"sqlite+aiosqlite:///{db_path}"), expire_on_commit=False)
    assert await SqlVerifiedStore(sm2).get("acme", "qms") == ["ISO 9001 held"]


async def test_verified_store_dedupe_and_tenant_scope(db_path):
    sm, _ = await _sessionmaker(db_path)
    vs = SqlVerifiedStore(sm)
    await vs.add("acme", "qms", "answer one")
    await vs.add("acme", "qms", "answer one")   # dedupe
    await vs.add("acme", "qms", "   ")           # empty ignored
    assert await vs.get("acme", "qms") == ["answer one"]
    assert await vs.get("beta", "qms") == []      # tenant-scoped


async def test_vector_store_tenant_scope(db_path):
    sm, _ = await _sessionmaker(db_path)
    vs = SqlVectorStore(sm)
    await vs.add(Passage(id="p1", tenant="acme", doc_id="d", text="hello", embedding=[0.1, 0.2]))
    await vs.add(Passage(id="p2", tenant="beta", doc_id="d", text="secret", embedding=[0.3]))
    acme = await vs.get("acme")
    assert [p.id for p in acme] == ["p1"] and acme[0].embedding == [0.1, 0.2]
    assert await vs.get("nobody") == []
