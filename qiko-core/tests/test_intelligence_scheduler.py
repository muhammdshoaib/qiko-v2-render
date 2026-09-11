from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.core.crypto import encrypt
from app.modules.intelligence.catalog import SourceCatalog
from app.modules.intelligence.models import InMemorySignalStore, Signal
from app.modules.intelligence.scheduler import _is_signal_source_due, sync_stale_signals


def _signal(tenant="acme", agent_id="a1", source="github", occurred_at=None):
    now = occurred_at or datetime.now(timezone.utc)
    return Signal(
        tenant=tenant, agent_id=agent_id, source=source, kind="commit",
        external_id="sha1", container="acme/repo", actor="dev", title="t", body="b",
        occurred_at=now)


async def test_source_with_no_signals_is_due():
    store = InMemorySignalStore()
    now = datetime.now(timezone.utc)
    due, since = await _is_signal_source_due(
        store, "acme", "a1", source="github", interval_minutes=60, now=now)
    assert due is True
    # No signal exists yet, so the bound floors to one interval back rather than defaulting to
    # an unbounded fetch: an unbounded fetch is only appropriate at connect time.
    assert since == now - timedelta(minutes=60)


async def test_source_with_a_fresh_signal_is_not_due():
    store = InMemorySignalStore()
    now = datetime.now(timezone.utc)
    occurred_at = now - timedelta(minutes=5)
    await store.add(_signal(occurred_at=occurred_at))
    due, since = await _is_signal_source_due(
        store, "acme", "a1", source="github", interval_minutes=60, now=now)
    assert due is False
    assert since == occurred_at


async def test_source_with_a_stale_signal_is_due():
    store = InMemorySignalStore()
    now = datetime.now(timezone.utc)
    occurred_at = now - timedelta(minutes=90)
    await store.add(_signal(occurred_at=occurred_at))
    due, since = await _is_signal_source_due(
        store, "acme", "a1", source="github", interval_minutes=60, now=now)
    assert due is True
    # The bound is the freshest existing signal, i.e. an incremental fetch, not full history.
    assert since == occurred_at


# --- the sweep --------------------------------------------------------------------------------


@dataclass
class _FakeAgent:
    tenant: str
    id: str
    atype: str = "intelligence"
    config: dict = field(default_factory=dict)


class _FakeAgents:
    def __init__(self, agents):
        self._agents = agents

    async def list_all(self):
        return self._agents


class _FakeConnector:
    key = "github"

    def __init__(self, fails_for: set[str] | None = None):
        self.calls = []
        self._fails_for = fails_for or set()

    async def fetch_since(self, *, config, credential, since, tenant, agent_id, signal_store=None):
        self.calls.append((tenant, agent_id, since))
        if agent_id in self._fails_for:
            raise RuntimeError("connector failure")
        return []

    async def verify(self, *, config, credential):
        return {"ok": True}


async def test_sync_stale_signals_skips_agents_without_a_connected_source():
    catalog = SourceCatalog()
    connector = _FakeConnector()
    catalog.register(key="github", name="GitHub", connector=connector)
    agents = _FakeAgents([_FakeAgent(tenant="acme", id="a1", config={})])
    store = InMemorySignalStore()

    summary = await sync_stale_signals(catalog, store, agents=agents)

    assert connector.calls == []
    assert summary["considered"] == 1
    assert summary["synced"] == 0


async def test_sync_stale_signals_syncs_a_connected_and_due_source():
    catalog = SourceCatalog()
    connector = _FakeConnector()
    catalog.register(key="github", name="GitHub", connector=connector)
    agent = _FakeAgent(tenant="acme", id="a1", config={
        "github_credentials_added": True,
        "github_token_encrypted": encrypt("ghp_faketoken"),
        "github_repo_allowlist": ["acme/repo"],
    })
    agents = _FakeAgents([agent])
    store = InMemorySignalStore()
    now = datetime.now(timezone.utc)

    summary = await sync_stale_signals(catalog, store, agents=agents, now=now)

    assert len(connector.calls) == 1
    tenant, agent_id, since = connector.calls[0]
    assert (tenant, agent_id) == ("acme", "a1")
    assert summary["synced"] == 1


async def test_sync_stale_signals_bounds_since_when_no_prior_signal_exists():
    """No signal exists yet for this connected source: `since` must floor to one sweep interval
    back, not fall through to `ingest_source`'s `datetime.min` default, which would re-fetch a
    source's entire history on every tick."""
    catalog = SourceCatalog()
    connector = _FakeConnector()
    catalog.register(key="github", name="GitHub", connector=connector)
    agent = _FakeAgent(tenant="acme", id="a1", config={
        "github_credentials_added": True,
        "github_token_encrypted": encrypt("ghp_faketoken"),
        "github_repo_allowlist": ["acme/repo"],
    })
    agents = _FakeAgents([agent])
    store = InMemorySignalStore()
    now = datetime.now(timezone.utc)

    await sync_stale_signals(catalog, store, agents=agents, now=now, interval_minutes=60)

    assert len(connector.calls) == 1
    _, _, since = connector.calls[0]
    assert since == now - timedelta(minutes=60)
    assert since > datetime.min.replace(tzinfo=timezone.utc)


async def test_sync_stale_signals_bounds_since_to_the_freshest_existing_signal():
    """A signal already exists for this source: `since` should be that signal's timestamp, an
    incremental fetch, rather than a fixed interval or unbounded history."""
    catalog = SourceCatalog()
    connector = _FakeConnector()
    catalog.register(key="github", name="GitHub", connector=connector)
    agent = _FakeAgent(tenant="acme", id="a1", config={
        "github_credentials_added": True,
        "github_token_encrypted": encrypt("ghp_faketoken"),
        "github_repo_allowlist": ["acme/repo"],
    })
    agents = _FakeAgents([agent])
    store = InMemorySignalStore()
    now = datetime.now(timezone.utc)
    freshest = now - timedelta(minutes=90)
    await store.add(_signal(tenant="acme", agent_id="a1", occurred_at=freshest))

    summary = await sync_stale_signals(catalog, store, agents=agents, now=now, interval_minutes=60)

    assert len(connector.calls) == 1
    _, _, since = connector.calls[0]
    assert since == freshest
    assert summary["synced"] == 1


async def test_sync_stale_signals_survives_a_failing_source_and_isolates_it():
    """Mirrors sales_intelligence's
    test_scan_due_sources_survives_a_failing_source_and_fires_scan_failed: one agent's connector
    call blows up, but the sweep must not abort, and the other agent's due source still gets
    synced with its failure/success correctly attributed in the summary."""
    catalog = SourceCatalog()
    connector = _FakeConnector(fails_for={"broken"})
    catalog.register(key="github", name="GitHub", connector=connector)
    healthy = _FakeAgent(tenant="acme", id="healthy", config={
        "github_credentials_added": True,
        "github_token_encrypted": encrypt("ghp_faketoken"),
        "github_repo_allowlist": ["acme/repo"],
    })
    broken = _FakeAgent(tenant="acme", id="broken", config={
        "github_credentials_added": True,
        "github_token_encrypted": encrypt("ghp_faketoken"),
        "github_repo_allowlist": ["acme/repo"],
    })
    agents = _FakeAgents([broken, healthy])
    store = InMemorySignalStore()

    summary = await sync_stale_signals(catalog, store, agents=agents)

    assert summary["considered"] == 2
    assert summary["synced"] == 1
    assert summary["failed"] == 1
    assert {agent_id for _, agent_id, _ in connector.calls} == {"broken", "healthy"}


async def test_sync_stale_signals_skips_qiko_track_without_a_base_url():
    """A manually-connected worker can have project_keys but an empty qiko_track_base_url; the
    gate must require base_url too, matching every other qiko_track readiness check in
    router.py (_backlog_service_for_agent, get_agent_metrics)."""
    catalog = SourceCatalog()
    connector = _FakeConnector()
    connector.key = "qiko_track"
    catalog.register(key="qiko_track", name="Qiko Track", connector=connector)
    agent = _FakeAgent(tenant="acme", id="a1", config={
        "qiko_track_credentials_added": True,
        "qiko_track_token_encrypted": encrypt("qt_faketoken"),
        "qiko_track_project_keys": ["QIKO"],
        "qiko_track_base_url": "",
    })
    agents = _FakeAgents([agent])
    store = InMemorySignalStore()

    summary = await sync_stale_signals(catalog, store, agents=agents)

    assert connector.calls == []
    assert summary["synced"] == 0
    assert summary["failed"] == 0
