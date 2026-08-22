"""The Signal model, the store contract and the source catalog.

The store tests run against **both** implementations from one set of assertions. That is
deliberate: the in-memory store is what most tests drive and the SQL store is what ships, so a
divergence between them means the suite is green about something that is not deployed. Making
them share a contract is the only way to keep that honest.

Two properties the whole vertical rests on are pinned here: a signal is scoped to one worker
inside one tenant and nothing else can read it, and a new source can be added without editing
anything outside its own module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlSignalStore
from app.modules.intelligence.catalog import (
    Connector,
    SourceCatalog,
    UnknownSource,
)
from app.modules.intelligence.models import (
    DEFAULT_SIGNAL_LIMIT,
    InMemorySignalStore,
    Signal,
)


def _sig(**overrides) -> Signal:
    base = dict(
        tenant="t1", agent_id="w1", source="slack", kind="message",
        external_id="ev-1", container="T1/C1", actor="U1",
        title="pricing", body="we should fix the pricing page",
        occurred_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Signal(**base)


async def _sql_store(tmp_path) -> SqlSignalStore:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'signals.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlSignalStore(async_sessionmaker(engine, expire_on_commit=False))


@pytest.fixture(params=["memory", "sql"])
async def store(request, tmp_path):
    """Every store test runs twice, once per implementation."""
    if request.param == "memory":
        return InMemorySignalStore()
    return await _sql_store(tmp_path)


# --- the shape -------------------------------------------------------------------------------

def test_a_signal_defaults_to_no_correlation_and_no_flags():
    s = _sig()
    assert s.ref is None
    assert s.url is None
    assert s.tags == []
    assert s.flagged is False
    assert s.meta == {}


def test_container_and_ref_answer_different_questions():
    """`container` is WHERE it happened, `ref` is WHICH work item it concerns.

    Conflating them was the mistake worth avoiding: the digest groups by conversation, while
    correlation joins across sources on the work item. A Slack channel and a ticket key are not
    the same kind of thing and must not share a field.
    """
    s = _sig(container="T1/C1", ref="QIW-1004")
    assert s.container == "T1/C1"
    assert s.ref == "QIW-1004"


def test_the_dedupe_key_is_scoped_per_worker_and_source():
    """Two workers watching one workspace each keep their own copy, and two sources may
    legitimately use the same external id."""
    assert _sig(agent_id="w1").dedupe_key != _sig(agent_id="w2").dedupe_key
    assert _sig(source="slack").dedupe_key != _sig(source="github").dedupe_key
    assert _sig(tenant="t1").dedupe_key != _sig(tenant="t2").dedupe_key
    assert _sig(title="a").dedupe_key == _sig(title="b").dedupe_key, "content is not identity"


# --- the store contract, run against both implementations -------------------------------------

async def test_add_then_read_back(store):
    assert await store.add(_sig()) is True
    [got] = await store.list_recent("t1", "w1")
    assert got.title == "pricing"


async def test_every_field_survives_a_round_trip(store):
    await store.add(_sig(ref="QIW-1004", url="https://example.invalid/x", tags=["action"],
                         flagged=True, meta={"thread_ts": "123.456"}))
    [got] = await store.list_recent("t1", "w1")
    assert got.ref == "QIW-1004"
    assert got.url == "https://example.invalid/x"
    assert got.tags == ["action"]
    assert got.flagged is True
    assert got.meta == {"thread_ts": "123.456"}
    assert got.occurred_at.tzinfo is not None, "timestamps must come back timezone-aware"


async def test_the_same_external_id_is_ingested_once(store):
    """Every connector re-reads an overlapping window, so ingestion has to be idempotent."""
    assert await store.add(_sig(external_id="ev-1")) is True
    assert await store.add(_sig(external_id="ev-1", title="changed")) is False
    [got] = await store.list_recent("t1", "w1")
    assert got.title == "pricing", "a duplicate must not overwrite the original"


async def test_the_same_external_id_in_a_different_source_is_a_different_signal(store):
    await store.add(_sig(external_id="1", source="slack"))
    await store.add(_sig(external_id="1", source="github"))
    assert len(await store.list_recent("t1", "w1")) == 2


async def test_another_tenant_sees_nothing(store):
    await store.add(_sig(tenant="t1"))
    assert await store.list_recent("t2", "w1") == []


async def test_another_worker_in_the_same_tenant_sees_nothing(store):
    """The Slack foundation scoped only by tenant. Two workers would have shared a buffer."""
    await store.add(_sig(agent_id="w1"))
    assert await store.list_recent("t1", "w2") == []


async def test_reads_can_narrow_by_source_and_container(store):
    await store.add(_sig(external_id="a", source="slack", container="T1/C1"))
    await store.add(_sig(external_id="b", source="slack", container="T1/C2"))
    await store.add(_sig(external_id="c", source="github", container="qiko/qiko-v2"))

    assert len(await store.list_recent("t1", "w1")) == 3
    assert len(await store.list_recent("t1", "w1", source="slack")) == 2
    assert len(await store.list_recent("t1", "w1", container="T1/C1")) == 1


async def test_two_workspaces_sharing_a_channel_id_stay_separate(store):
    """A channel id is unique only within a workspace, which is why container carries the team."""
    await store.add(_sig(external_id="a", container="T1/C1", body="ours"))
    await store.add(_sig(external_id="b", container="T2/C1", body="theirs"))
    [got] = await store.list_recent("t1", "w1", container="T1/C1")
    assert got.body == "ours"


async def test_the_window_and_the_limit_both_bound_a_read(store):
    now = datetime.now(timezone.utc)
    await store.add(_sig(external_id="old", occurred_at=now - timedelta(days=30)))
    for i in range(10):
        await store.add(_sig(external_id=f"r{i}", occurred_at=now - timedelta(minutes=10 - i)))

    windowed = await store.list_recent("t1", "w1", since=now - timedelta(hours=1))
    assert "old" not in [s.external_id for s in windowed]

    limited = await store.list_recent("t1", "w1", limit=3)
    assert [s.external_id for s in limited] == ["r7", "r8", "r9"], "newest N, oldest-first"


async def test_the_default_limit_is_applied_rather_than_unbounded(store):
    now = datetime.now(timezone.utc)
    for i in range(DEFAULT_SIGNAL_LIMIT + 25):
        await store.add(_sig(external_id=f"s{i}", occurred_at=now - timedelta(seconds=i)))
    assert len(await store.list_recent("t1", "w1")) == DEFAULT_SIGNAL_LIMIT


async def test_clearing_a_container_leaves_every_other_one_intact(store):
    await store.add(_sig(external_id="a", container="T1/C1"))
    await store.add(_sig(external_id="b", container="T1/C2"))
    await store.add(_sig(external_id="c", tenant="t2", container="T1/C1"))

    assert await store.clear("t1", "w1", container="T1/C1") == 1
    assert [s.external_id for s in await store.list_recent("t1", "w1")] == ["b"]
    assert len(await store.list_recent("t2", "w1")) == 1, "another tenant is untouched"


async def test_clearing_without_a_container_clears_the_whole_worker(store):
    await store.add(_sig(external_id="a", container="T1/C1"))
    await store.add(_sig(external_id="b", container="T1/C2"))
    await store.add(_sig(external_id="c", agent_id="w2"))
    assert await store.clear("t1", "w1") == 2
    assert len(await store.list_recent("t1", "w2")) == 1, "another worker is untouched"


async def test_retention_drops_only_what_is_past_the_window(store):
    now = datetime.now(timezone.utc)
    await store.add(_sig(external_id="fresh", occurred_at=now))
    await store.add(_sig(external_id="stale", occurred_at=now - timedelta(days=30)))
    assert await store.purge_older_than(timedelta(days=7)) == 1
    assert [s.external_id for s in await store.list_recent("t1", "w1")] == ["fresh"]


# --- the catalog -----------------------------------------------------------------------------

class _FakeConnector:
    key = "fake"

    def __init__(self) -> None:
        self.verified = False

    async def fetch_since(self, *, config, credential, since, tenant, agent_id,
                          signal_store=None):
        return [_sig(source="fake", external_id="from-connector")]

    async def verify(self, *, config, credential):
        self.verified = True
        return {"ok": True}


def test_a_source_is_added_by_registering_one_entry():
    catalog = SourceCatalog()
    catalog.register(key="fake", name="Fake", connector=_FakeConnector())
    assert catalog.keys() == ["fake"]
    assert catalog.definition("fake").name == "Fake"


def test_a_source_can_emit_without_a_connector():
    """Uploads and research produce signals directly; they are sources but nothing polls them."""
    catalog = SourceCatalog()
    catalog.register(key="upload", name="Uploaded documents", connector=None)
    assert catalog.definition("upload").pollable is False
    assert catalog.pollable_keys() == []


def test_a_registered_connector_is_pollable():
    catalog = SourceCatalog()
    catalog.register(key="fake", name="Fake", connector=_FakeConnector())
    assert catalog.definition("fake").pollable is True
    assert catalog.pollable_keys() == ["fake"]


def test_an_unknown_source_is_refused_rather_than_guessed():
    catalog = SourceCatalog()
    with pytest.raises(UnknownSource):
        catalog.connector_for("nope")
    assert catalog.definition("nope") is None


def test_a_source_with_no_connector_cannot_be_polled():
    catalog = SourceCatalog()
    catalog.register(key="upload", name="Uploaded documents", connector=None)
    with pytest.raises(UnknownSource):
        catalog.connector_for("upload")


def test_registering_the_same_key_twice_is_refused():
    """Two connectors answering to one key means dispatch depends on import order."""
    catalog = SourceCatalog()
    catalog.register(key="fake", name="Fake", connector=_FakeConnector())
    with pytest.raises(ValueError):
        catalog.register(key="fake", name="Other", connector=_FakeConnector())


def test_the_catalog_serialises_for_the_frontend():
    catalog = SourceCatalog()
    catalog.register(key="fake", name="Fake", connector=_FakeConnector(),
                     description="A fake source")
    [item] = catalog.items()
    assert item == {"key": "fake", "name": "Fake", "description": "A fake source",
                    "pollable": True, "connected": False, "configured": True}


def test_the_catalog_reports_which_sources_this_worker_has_connected():
    catalog = SourceCatalog()
    catalog.register(key="fake", name="Fake", connector=_FakeConnector())
    catalog.register(key="upload", name="Uploads", connector=None)
    connected = {i["key"]: i["connected"] for i in catalog.items(connected={"fake"})}
    assert connected == {"fake": True, "upload": False}


def test_a_connector_satisfies_the_protocol():
    assert isinstance(_FakeConnector(), Connector)


async def test_verify_is_reachable_through_the_catalog():
    catalog = SourceCatalog()
    connector = _FakeConnector()
    catalog.register(key="fake", name="Fake", connector=connector)
    assert await catalog.connector_for("fake").verify(config={}, credential="x") == {"ok": True}
    assert connector.verified is True
