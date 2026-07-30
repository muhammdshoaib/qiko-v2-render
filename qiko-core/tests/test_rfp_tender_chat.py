"""Per-tender cockpit chat persistence: POST /rfp/packs/{id}/chat stores both turns and
GET /rfp/packs/{id}/chat/history reads them back in order, tenant-scoped, and it works over the
SQL-backed chat store (so the conversation survives a restart, not just in process memory)."""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Agent as AgentRow
from app.db.models import Tenant
from app.db.stores import SqlChatStore
from app.modules.ai.gateway import LLMResponse
from app.modules.chat.service import ChatService

from tests.helpers import auth_cookies, autoseed_rfp_pack_workers


@pytest.fixture(autouse=True)
def _seed_pack_workers(client, monkeypatch):
    autoseed_rfp_pack_workers(client, monkeypatch)


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text)


def _canned(monkeypatch, text: str) -> None:
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(text))


def test_tender_chat_persists_both_turns_and_history_reads_in_order(client, monkeypatch):
    _canned(monkeypatch, "Our HR system is ISO 27001 certified.")
    c = auth_cookies("tchat1", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()

    # Empty before any exchange.
    assert client.get(f"/api/v1/rfp/packs/{pack['id']}/chat/history", cookies=c).json() == []

    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/chat", cookies=c,
                    json={"question": "How secure is our HR system?"})
    assert r.status_code == 200
    assert "ISO 27001" in r.json()["answer"]

    _canned(monkeypatch, "It was developed in 2019.")
    r2 = client.post(f"/api/v1/rfp/packs/{pack['id']}/chat", cookies=c,
                     json={"question": "When was it developed?"})
    assert r2.status_code == 200

    hist = client.get(f"/api/v1/rfp/packs/{pack['id']}/chat/history", cookies=c).json()
    assert [(m["role"], m["text"]) for m in hist] == [
        ("user", "How secure is our HR system?"),
        ("assistant", "Our HR system is ISO 27001 certified."),
        ("user", "When was it developed?"),
        ("assistant", "It was developed in 2019."),
    ]


def test_tender_chat_history_404_for_unknown_pack(client):
    c = auth_cookies("tchat2", "owner")
    r = client.get("/api/v1/rfp/packs/missing/chat/history", cookies=c)
    assert r.status_code == 404


def test_tender_chat_history_is_tenant_scoped(client, monkeypatch):
    """A pack + conversation in one tenant is invisible (404) to another tenant -- the pack lookup
    is tenant-scoped, so a cross-tenant read never leaks the stored conversation."""
    _canned(monkeypatch, "Answer.")
    owner = auth_cookies("tchatA", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=owner).json()
    client.post(f"/api/v1/rfp/packs/{pack['id']}/chat", cookies=owner, json={"question": "Q?"})

    other = auth_cookies("tchatB", "owner")
    assert client.get(f"/api/v1/rfp/packs/{pack['id']}/chat/history", cookies=other).status_code == 404


def test_tender_chat_persists_via_sql_store(client, monkeypatch, tmp_path):
    """Wire the app to a Postgres-shaped chat store (aiosqlite file) so the exchange is written to
    the DB, then read it back through a FRESH ChatService over a FRESH engine on the SAME file
    (simulating a restart) to prove the conversation survives beyond process memory.

    Each engine is created/disposed inside its own event loop: the TestClient drives the app on its
    own portal loop, so schema setup and the "reborn" read each run on separate short-lived loops
    against the same on-disk sqlite file (committed data is visible across connections)."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}"

    async def _create_schema() -> None:
        engine = create_async_engine(db_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as session, session.begin():
            session.add(Tenant(id="tchatsql", name="Tender Chat"))
            session.add(AgentRow(id="w1", tenant_id="tchatsql", name="Worker", enabled=True))
        await engine.dispose()

    asyncio.run(_create_schema())

    # The store the app writes through, on its own engine (used within the TestClient loop).
    client.app.state.chat = ChatService(store=SqlChatStore(
        async_sessionmaker(create_async_engine(db_url), expire_on_commit=False)))

    _canned(monkeypatch, "Grounded reply.")
    c = auth_cookies("tchatsql", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    assert client.post(f"/api/v1/rfp/packs/{pack['id']}/chat", cookies=c,
                       json={"question": "Question?"}).status_code == 200

    async def _read_after_restart() -> list[tuple[str, str]]:
        engine = create_async_engine(db_url)
        reborn = ChatService(store=SqlChatStore(async_sessionmaker(engine, expire_on_commit=False)))
        hist = await reborn.history("tchatsql", f"tender:{pack['id']}", limit=500)
        await engine.dispose()
        return [(m.role, m.text) for m in hist]

    assert asyncio.run(_read_after_restart()) == [
        ("user", "Question?"), ("assistant", "Grounded reply.")]
