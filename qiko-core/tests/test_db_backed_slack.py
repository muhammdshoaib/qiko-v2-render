"""The DURABLE Slack stores (exercised on sqlite).

These exist because the tenant-isolation controls for the Slack assistant live in the SQL
predicates, and the rest of the suite drives the in-memory stores: without this file every BOLA
test would still pass if `team_id` were dropped from the queries or the ambiguity refusal were
deleted, because nothing would execute the code that actually runs in production.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.stores import SqlSlackChannelStore
from app.db.sync_stores import SqlSlackInstallationStore
from app.modules.channels.slack_oauth import SlackInstallation
from app.modules.channels.slack_store import SlackMessage, slack_ts
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.store import InMemoryVectorStore


def _msg(*, tenant="t1", agent_id="w1", team="T1", channel="C1", text="hello", ts=None,
         enterprise=None) -> SlackMessage:
    return SlackMessage(
        tenant=tenant, agent_id=agent_id, team_id=team, channel_id=channel,
        channel_type="channel", thread_ts=None, user_id="U1", text=text,
        ts=ts if ts is not None else slack_ts(datetime.now(timezone.utc)),
        enterprise_id=enterprise)


async def _messages(path) -> SqlSlackChannelStore:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlSlackChannelStore(async_sessionmaker(engine, expire_on_commit=False))


def _installs(path) -> SqlSlackInstallationStore:
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return SqlSlackInstallationStore(sessionmaker(engine, expire_on_commit=False))


# --- the ts format both stores depend on ------------------------------------------------------

def test_the_slack_ts_format_is_fixed_width_so_string_order_is_numeric_order():
    """Both stores range-scan and sort `ts` as a STRING. That is only correct while the width is
    constant, so this pins the property the rest of the file relies on. Note `str(float)` does NOT
    have it: it renders 1767225600.07 for a value the DB must compare as 1767225600.070000."""
    import random

    assert slack_ts(datetime(2026, 1, 1, tzinfo=timezone.utc)) == "1767225600.000000"
    assert len(slack_ts(datetime.now(timezone.utc))) == 17

    moments = sorted(datetime.fromtimestamp(random.uniform(1.4e9, 1.8e9), tz=timezone.utc)
                     for _ in range(500))
    rendered = [slack_ts(m) for m in moments]
    assert rendered == sorted(rendered), "lexicographic order must match chronological order"


# --- the message buffer ----------------------------------------------------------------------

async def test_a_round_trip_preserves_the_message(tmp_path):
    store = await _messages(tmp_path / "m.db")
    await store.add(_msg(text="fix pricing", ts="1700000000.100000"))
    [stored] = await store.list_recent("t1", "w1", "T1", "C1",
                                         datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert (stored.tenant, stored.team_id, stored.channel_id) == ("t1", "T1", "C1")
    assert stored.text == "fix pricing"
    assert stored.enterprise_id is None


async def test_another_tenant_cannot_read_or_clear_the_channel(tmp_path):
    store = await _messages(tmp_path / "m.db")
    await store.add(_msg(tenant="t1", ts="1700000000.100000"))
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)

    assert await store.list_recent("t2", "w1", "T1", "C1", since) == []
    assert await store.clear_channel("t2", "w1", "T1", "C1") == 0
    assert len(await store.list_recent("t1", "w1", "T1", "C1", since)) == 1


async def test_a_second_workspace_sharing_a_channel_id_is_not_read_or_cleared(tmp_path):
    """A channel id is unique only WITHIN a workspace, so team_id has to be in every predicate."""
    store = await _messages(tmp_path / "m.db")
    await store.add(_msg(team="T1", text="ours", ts="1700000000.100000"))
    await store.add(_msg(team="T2", text="theirs", ts="1700000000.200000"))
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)

    ours = await store.list_recent("t1", "w1", "T1", "C1", since)
    assert [m.text for m in ours] == ["ours"]

    assert await store.clear_channel("t1", "w1", "T1", "C1") == 1
    remaining = await store.list_recent("t1", "w1", "T2", "C1", since)
    assert [m.text for m in remaining] == ["theirs"]


async def test_the_window_and_the_limit_both_bound_the_read(tmp_path):
    store = await _messages(tmp_path / "m.db")
    now = datetime.now(timezone.utc)
    await store.add(_msg(text="ancient", ts=slack_ts(now - timedelta(days=3))))
    for i in range(10):
        await store.add(_msg(text=f"recent-{i}", ts=slack_ts(now - timedelta(minutes=10 - i))))

    windowed = await store.list_recent("t1", "w1", "T1", "C1", now - timedelta(hours=1))
    assert "ancient" not in [m.text for m in windowed]

    limited = await store.list_recent("t1", "w1", "T1", "C1", now - timedelta(days=7), limit=3)
    # Newest three, oldest-first, so the transcript still reads in order.
    assert [m.text for m in limited] == ["recent-7", "recent-8", "recent-9"]


async def test_retention_deletes_only_what_is_past_the_window(tmp_path):
    store = await _messages(tmp_path / "m.db")
    await store.add(_msg(text="keep"))
    assert await store.purge_older_than(timedelta(days=7)) == 0
    assert len(await store.list_recent(
        "t1", "w1", "T1", "C1", datetime(2020, 1, 1, tzinfo=timezone.utc))) == 1
    # A zero-length window makes everything older than "now", which is the observable proof the
    # cutoff is applied rather than the table simply being truncated.
    assert await store.purge_older_than(timedelta(seconds=0)) == 1


# --- installations --------------------------------------------------------------------------

def test_an_installation_round_trips_with_the_token_encrypted_at_rest(tmp_path):
    store = _installs(tmp_path / "i.db")
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-secret", bot_user_id="B1",
                                 tenant="t1", worker_id="w1"))

    fetched = store.fetch("T1", tenant="t1")
    assert fetched.bot_token == "xoxb-secret"

    # The stored column must not contain the plaintext.
    with store.sessionmaker() as session:
        from app.db.models import SlackInstallation as Row
        row = session.get(Row, ("T1", "-", "t1"))
        assert "xoxb-secret" not in row.bot_token_encrypted


def test_the_reverse_lookup_resolves_a_single_installed_workspace(tmp_path):
    store = _installs(tmp_path / "i.db")
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-1", bot_user_id="B1", tenant="t1"))
    resolved = store.fetch_by_workspace("T1")
    assert (resolved.tenant, resolved.bot_token) == ("t1", "xoxb-1")


def test_an_ambiguous_workspace_resolves_to_nothing(tmp_path):
    """Two tenants, one workspace. Answering would pick a tenant by query order."""
    store = _installs(tmp_path / "i.db")
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-1", bot_user_id="B1", tenant="t1"))
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-2", bot_user_id="B2", tenant="t2"))
    assert store.fetch_by_workspace("T1") is None


def test_a_tenantless_installation_is_refused(tmp_path):
    store = _installs(tmp_path / "i.db")
    with pytest.raises(ValueError):
        store.save(SlackInstallation(team_id="T1", bot_token="xoxb-1", bot_user_id="B1"))
    assert store.fetch_by_workspace("T1") is None


def test_an_enterprise_installation_is_keyed_separately_from_the_plain_one(tmp_path):
    store = _installs(tmp_path / "i.db")
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-plain", bot_user_id="B1",
                                 tenant="t1"))
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-grid", bot_user_id="B1",
                                 enterprise_id="E9", tenant="t1"))

    assert store.fetch_by_workspace("T1").bot_token == "xoxb-plain"
    grid = store.fetch_by_workspace("T1", "E9")
    assert grid.bot_token == "xoxb-grid"
    assert grid.enterprise_id == "E9"


def test_saving_the_same_workspace_twice_rotates_rather_than_duplicates(tmp_path):
    store = _installs(tmp_path / "i.db")
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-old", bot_user_id="B1", tenant="t1"))
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-new", bot_user_id="B1", tenant="t1"))
    # Still unambiguous, so a re-install must not look like two tenants.
    assert store.fetch_by_workspace("T1").bot_token == "xoxb-new"


def test_delete_removes_only_the_named_installation(tmp_path):
    store = _installs(tmp_path / "i.db")
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-1", bot_user_id="B1", tenant="t1"))
    store.save(SlackInstallation(team_id="T2", bot_token="xoxb-2", bot_user_id="B2", tenant="t1"))
    store.delete("T1", tenant="t1")
    assert store.fetch("T1", tenant="t1") is None
    assert store.fetch("T2", tenant="t1") is not None


async def test_a_captured_message_is_ingested_into_knowledge(tmp_path):
    """QIW-1004: signals enter the worker's knowledge corpus as they arrive, not in a later digest."""
    knowledge = KnowledgeService(store=InMemoryVectorStore())
    store = await _messages(tmp_path / "m.db")
    store.knowledge = knowledge
    await store.add(_msg(text="we decided to keep pricing flat", ts="1700000000.100000"))

    passages = await knowledge.retrieve("t1", "pricing decision", k=1, agent_id="w1")
    assert len(passages) == 1
    assert "we decided to keep pricing flat" in passages[0].text
    expected_url = "https://app.slack.com/client/T1/C1/1700000000.100000"
    assert passages[0].doc_id == expected_url


async def test_a_duplicate_slack_event_is_not_ingested_twice(tmp_path):
    """The signal store dedupes; the knowledge store must stay deduped too."""
    knowledge = KnowledgeService(store=InMemoryVectorStore())
    store = await _messages(tmp_path / "m.db")
    store.knowledge = knowledge
    msg = _msg(text="we decided to keep pricing flat", ts="1700000000.100000")
    assert await store.add(msg) is True
    assert await store.add(msg) is False
    passages = await knowledge.retrieve("t1", "pricing", k=5, agent_id="w1")
    assert len(passages) == 1


async def test_clear_channel_also_deletes_knowledge_passages(tmp_path):
    """Signal retention must keep the knowledge corpus in sync: no orphan passages."""
    knowledge = KnowledgeService(store=InMemoryVectorStore())
    store = await _messages(tmp_path / "m.db")
    store.knowledge = knowledge
    await store.add(_msg(text="we decided to keep pricing flat", ts="1700000000.100000"))
    assert len(await knowledge.retrieve("t1", "pricing", k=5, agent_id="w1")) == 1

    assert await store.clear_channel("t1", "w1", "T1", "C1") == 1
    assert await knowledge.retrieve("t1", "pricing", k=5, agent_id="w1") == []


async def test_purge_older_than_also_deletes_knowledge_passages(tmp_path):
    """Retention across the Slack buffer cascades to the vector store."""
    knowledge = KnowledgeService(store=InMemoryVectorStore())
    store = await _messages(tmp_path / "m.db")
    store.knowledge = knowledge
    old = datetime.now(timezone.utc) - timedelta(days=8)
    await store.add(_msg(text="we decided to keep pricing flat", ts=slack_ts(old)))
    assert len(await knowledge.retrieve("t1", "pricing", k=5, agent_id="w1")) == 1

    assert await store.purge_older_than(timedelta(days=7)) == 1
    assert await knowledge.retrieve("t1", "pricing", k=5, agent_id="w1") == []
