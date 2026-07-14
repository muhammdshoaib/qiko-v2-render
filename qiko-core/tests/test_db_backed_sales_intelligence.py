"""Postgres-backed sales-intelligence stores over the Sql* stores (exercised on aiosqlite),
mirroring tests/test_persistence.py for the CRM/other DB stores. Confirms tenant scoping
(BOLA-safe), persistence across a simulated restart, and Fernet-at-rest for Salesforce tokens.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.crypto import decrypt, encrypt
from app.db.base import Base
from app.db.stores import (
    SqlActivityLogStore,
    SqlIngestionSourceStore,
    SqlOpportunityStore,
    SqlSalesforceConnectionStore,
)
from app.modules.sales_intelligence.models import ActivityLog, Opportunity


async def _sessionmaker(path: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "sales.db")


_SOURCE_DEFAULTS = {"name": "UNGM Public Notices", "type": "portal", "status": "inactive",
                    "auth_status": "public_details_limited", "scan_cadence": "every_1_minute",
                    "config": {"url": "https://www.ungm.org/Public/Notice"}}


async def test_ingestion_source_get_or_create_is_idempotent_and_tenant_scoped(db_path):
    sm, _ = await _sessionmaker(db_path)
    store = SqlIngestionSourceStore(sm)
    first = await store.get_or_create("acme", "ag1", "ungm", _SOURCE_DEFAULTS)
    again = await store.get_or_create("acme", "ag1", "ungm", _SOURCE_DEFAULTS)
    assert first.id == again.id  # no duplicate row
    assert first.name == "UNGM Public Notices" and first.config["url"].endswith("/Notice")
    # tenant + agent scoped
    assert await store.get("beta", "ag1", "ungm") is None
    assert await store.get("acme", "ag2", "ungm") is None
    assert (await store.get("acme", "ag1", "ungm")).id == first.id


async def test_ingestion_source_update_status_and_list_active_persist(db_path):
    sm1, e1 = await _sessionmaker(db_path)
    store1 = SqlIngestionSourceStore(sm1)
    source = await store1.get_or_create("acme", "ag1", "ungm", _SOURCE_DEFAULTS)
    source.status = "active"
    source.opportunities_found = 3
    await store1.update(source)
    await e1.dispose()  # simulate redeploy/restart

    sm2 = async_sessionmaker(create_async_engine(f"sqlite+aiosqlite:///{db_path}"), expire_on_commit=False)
    store2 = SqlIngestionSourceStore(sm2)
    reloaded = await store2.get("acme", "ag1", "ungm")
    assert reloaded.status == "active" and reloaded.opportunities_found == 3
    assert [s.source_key for s in await store2.list_for_agent("acme", "ag1")] == ["ungm"]
    assert [s.tenant for s in await store2.list_active()] == ["acme"]
    assert await store2.list_active("beta") == []  # tenant scoped


def _opp(**kw) -> Opportunity:
    base = dict(id="op1", tenant="acme", agent_id="ag1", external_id="ext-1", source_key="ungm",
                source_name="UNGM Public Notices", title="Security guarding services", stage="ingested")
    base.update(kw)
    return Opportunity(**base)


async def test_opportunity_add_find_get_and_tenant_scope(db_path):
    sm, _ = await _sessionmaker(db_path)
    store = SqlOpportunityStore(sm)
    await store.add(_opp(estimated_value=500000.0, currency="USD", risks=["late deadline"]))

    found = await store.find_by_external_id("acme", "ag1", "ungm", "ext-1")
    assert found is not None and found.estimated_value == 500000.0 and found.risks == ["late deadline"]
    assert await store.find_by_external_id("beta", "ag1", "ungm", "ext-1") is None  # tenant scoped
    assert await store.get("acme", "ag1", "op1") is not None
    assert await store.get("acme", "ag2", "op1") is None  # agent scoped
    assert await store.get("beta", "ag1", "op1") is None  # tenant scoped


async def test_opportunity_update_and_list_filters_exclude_archived_and_deleted(db_path):
    sm1, e1 = await _sessionmaker(db_path)
    store1 = SqlOpportunityStore(sm1)
    await store1.add(_opp(id="op1", external_id="e1", title="Guarding", stage="qualified",
                          recommendation="Bid"))
    await store1.add(_opp(id="op2", external_id="e2", title="CCTV", stage="ingested"))
    archived = _opp(id="op3", external_id="e3", title="Old tender")
    from datetime import datetime, timezone
    archived.archived_at = datetime.now(timezone.utc)
    await store1.add(archived)
    deleted = _opp(id="op4", external_id="e4", title="Removed")
    deleted.deleted_at = datetime.now(timezone.utc)
    await store1.add(deleted)
    await e1.dispose()  # simulate redeploy/restart

    sm2 = async_sessionmaker(create_async_engine(f"sqlite+aiosqlite:///{db_path}"), expire_on_commit=False)
    store2 = SqlOpportunityStore(sm2)
    default = await store2.list_for_agent("acme", "ag1")
    ids = {o.id for o in default}
    assert ids == {"op1", "op2"}  # archived + deleted hidden by default
    assert [o.id for o in await store2.list_for_agent("acme", "ag1", stage="qualified")] == ["op1"]
    assert [o.id for o in await store2.list_for_agent("acme", "ag1", recommendation="Bid")] == ["op1"]
    assert [o.id for o in await store2.list_for_agent("acme", "ag1", archived_only=True)] == ["op3"]
    assert {o.id for o in await store2.list_for_agent("acme", "ag1", include_archived=True)} == {"op1", "op2", "op3"}
    assert await store2.list_for_agent("beta", "ag1") == []  # tenant scoped

    op1 = await store2.get("acme", "ag1", "op1")
    op1.stage = "validated"
    op1.human_review_notes = "looks good"
    await store2.update(op1)
    assert (await store2.get("acme", "ag1", "op1")).stage == "validated"


async def test_opportunity_list_with_deadline_is_cross_tenant_and_excludes_archived_deleted(db_path):
    from datetime import datetime, timedelta, timezone

    sm, _ = await _sessionmaker(db_path)
    store = SqlOpportunityStore(sm)
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    # two live opportunities with deadlines, in DIFFERENT tenants (the scheduler sweeps globally)
    await store.add(_opp(id="d1", tenant="acme", external_id="e1", deadline_at=soon))
    await store.add(_opp(id="d2", tenant="beta", external_id="e2", deadline_at=soon))
    # excluded: no deadline / archived / soft-deleted
    await store.add(_opp(id="d3", external_id="e3", deadline_at=None))
    archived = _opp(id="d4", external_id="e4", deadline_at=soon)
    archived.archived_at = datetime.now(timezone.utc)
    await store.add(archived)
    deleted = _opp(id="d5", external_id="e5", deadline_at=soon)
    deleted.deleted_at = datetime.now(timezone.utc)
    await store.add(deleted)

    with_deadline = await store.list_with_deadline()
    assert {o.id for o in with_deadline} == {"d1", "d2"}


async def test_activity_log_add_list_filters_order_and_scope(db_path):
    sm, _ = await _sessionmaker(db_path)
    store = SqlActivityLogStore(sm)
    await store.add(ActivityLog(id="l1", tenant="acme", agent_id="ag1", action="opportunity_ingested",
                                opportunity_id="op1", tone="success", metadata={"source_key": "ungm"}))
    await store.add(ActivityLog(id="l2", tenant="acme", agent_id="ag1", action="ungm_scan_completed",
                                metadata={"source_key": "ungm"}))
    await store.add(ActivityLog(id="l3", tenant="beta", agent_id="ag1", action="opportunity_ingested"))

    all_acme = await store.list_for_agent("acme", "ag1")
    assert {log.id for log in all_acme} == {"l1", "l2"}  # tenant scoped
    # activity_type derived from action in __post_init__ round-trips through the DB
    assert [log.id for log in await store.list_for_agent("acme", "ag1", activity_type="source_scan")] == ["l2"]
    assert [log.id for log in await store.list_for_agent("acme", "ag1", opportunity_id="op1")] == ["l1"]
    assert [log.id for log in await store.list_for_agent("acme", "ag1", action="ungm_scan_completed")] == ["l2"]
    assert len(await store.list_for_agent("acme", "ag1", limit=1)) == 1
    assert (await store.list_for_agent("acme", "ag1"))[0].metadata == {"source_key": "ungm"}


async def test_salesforce_connection_tokens_encrypted_at_rest_and_persist(db_path):
    sm1, e1 = await _sessionmaker(db_path)
    store1 = SqlSalesforceConnectionStore(sm1)
    conn = await store1.get_or_create("acme", "ag1")
    assert conn.status == "disconnected" and conn.access_token is None

    # Service layer hands the store already-Fernet-encrypted tokens (see salesforce.py); the
    # store persists the ciphertext verbatim -- assert the DB column never holds plaintext.
    conn.status = "connected"
    conn.instance_url = "https://acme.my.salesforce.com"
    conn.access_token = encrypt("SECRET-ACCESS")
    conn.refresh_token = encrypt("SECRET-REFRESH")
    await store1.update(conn)

    async with sm1() as s:
        raw = (await s.execute(text(
            "SELECT enc_access_token, enc_refresh_token FROM sales_intel_salesforce_connections"))).first()
    assert "SECRET-ACCESS" not in raw[0] and "SECRET-REFRESH" not in raw[1]  # ciphertext at rest
    assert decrypt(raw[0]) == "SECRET-ACCESS" and decrypt(raw[1]) == "SECRET-REFRESH"
    await e1.dispose()  # simulate redeploy/restart

    sm2 = async_sessionmaker(create_async_engine(f"sqlite+aiosqlite:///{db_path}"), expire_on_commit=False)
    reloaded = await SqlSalesforceConnectionStore(sm2).get_or_create("acme", "ag1")
    assert reloaded.status == "connected" and reloaded.is_connected()
    assert decrypt(reloaded.access_token) == "SECRET-ACCESS"
    assert decrypt(reloaded.refresh_token) == "SECRET-REFRESH"
    # tenant + agent scoped: a different key starts fresh (disconnected)
    assert (await SqlSalesforceConnectionStore(sm2).get_or_create("beta", "ag1")).access_token is None
