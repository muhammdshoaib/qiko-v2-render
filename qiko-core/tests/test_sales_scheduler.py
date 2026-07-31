"""Background scheduler sweeps for Sales Intelligence (app.modules.sales_intelligence.scheduler):
the arq-cron analogue of the idg-sales Laravel scheduler. Exercised over the in-memory stores so
no Redis/DB is needed -- the sweeps are store-agnostic and drive the same OpportunityService the
manual API endpoints use.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.agents.service import Agent
from app.modules.notifications.models import (
    InMemoryNotificationStore,
    TYPE_DEADLINE_REMINDER,
    TYPE_SCAN_FAILED,
)
from app.modules.notifications.service import NotificationService
from app.modules.sales_intelligence import scheduler
from app.modules.sales_intelligence.models import Opportunity
from app.modules.sales_intelligence.notifications import SalesNotificationService
from app.modules.sales_intelligence.service import OpportunityService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build() -> tuple[OpportunityService, InMemoryNotificationStore]:
    inbox = InMemoryNotificationStore()
    notifier = SalesNotificationService(notifications=NotificationService(store=inbox))

    class Agents:
        async def get(self, tenant: str, agent_id: str):
            return Agent(id=agent_id, tenant=tenant, name="Sales", enabled=True)

    svc = OpportunityService(scan_interval_minutes=1, notifier=notifier, agents=Agents())
    return svc, inbox


def _notifications_of_type(inbox: InMemoryNotificationStore, type_: str) -> list:
    return [n for n in inbox._by_id.values() if n.type == type_]


def _ted_notice(external_id: str = "T-1") -> dict:
    return {"payload": {}, "total_notice_count": 1, "skipped": 0, "notices": [{
        "external_id": external_id, "title": "Static security guarding services",
        "buyer": "Ministry of Interior", "country": "United Arab Emirates",
        "category": "Security services", "estimated_value": 500000, "currency": "USD",
        "deadline_at": _now() + timedelta(days=30),
    }]}


# --- scan_due_sources ---
async def test_scan_due_sources_scans_a_due_source(monkeypatch):
    svc, _ = _build()
    await svc.update_source_status("acme", "agent-1", "ted", "active")  # last_scan_at stays None -> due
    monkeypatch.setattr(svc.ted, "search", lambda filters=None: _ted_notice())

    summary = await scheduler.scan_due_sources(svc)

    assert summary == {"active_sources": 1, "scanned": 1, "skipped": 0, "failed": 0}
    opps = await svc.opportunities.list_for_agent("acme", "agent-1")
    assert len(opps) == 1


async def test_scan_due_sources_skips_a_not_due_source(monkeypatch):
    svc, _ = _build()
    now = _now()
    await svc.update_source_status("acme", "agent-1", "ted", "active")
    source = await svc.sources.get("acme", "agent-1", "ted")
    source.last_scan_at = now  # just scanned -> not due for another interval
    await svc.sources.update(source)

    called = False

    def _search(filters=None):
        nonlocal called
        called = True
        return _ted_notice()

    monkeypatch.setattr(svc.ted, "search", _search)
    summary = await scheduler.scan_due_sources(svc, now=now)

    assert summary == {"active_sources": 1, "scanned": 0, "skipped": 1, "failed": 0}
    assert called is False


async def test_scan_due_sources_survives_a_failing_source_and_fires_scan_failed(monkeypatch):
    svc, inbox = _build()
    await svc.update_source_status("acme", "agent-1", "ungm", "active")
    await svc.update_source_status("acme", "agent-1", "ted", "active")

    def _boom(filters=None):
        raise RuntimeError("portal down")

    monkeypatch.setattr(svc.ungm, "search", _boom)
    monkeypatch.setattr(svc.ted, "search", lambda filters=None: _ted_notice())

    summary = await scheduler.scan_due_sources(svc)

    # one failed, but the sweep continued and scanned the healthy source
    assert summary["scanned"] == 1
    assert summary["failed"] == 1
    scan_failed = _notifications_of_type(inbox, TYPE_SCAN_FAILED)
    assert len(scan_failed) == 1
    assert scan_failed[0].metadata["sourceKey"] == "ungm"
    # the healthy source produced an opportunity
    assert len(await svc.opportunities.list_for_agent("acme", "agent-1")) == 1


async def test_scan_due_sources_no_active_sources_is_clean():
    svc, _ = _build()
    summary = await scheduler.scan_due_sources(svc)
    assert summary == {"active_sources": 0, "scanned": 0, "skipped": 0, "failed": 0}


async def test_scan_due_sources_honours_per_source_cadence(monkeypatch):
    """Due-ness is derived from each source's own cadence, not the global interval: an hourly
    source scanned 30 min ago is not yet due, but is once its 60-minute interval elapses."""
    svc, _ = _build()  # global interval = 1 minute
    now = _now()
    await svc.update_source_status("acme", "agent-1", "ted", "active")
    await svc.update_source_cadence("acme", "agent-1", "ted", "hourly")
    ted = await svc.sources.get("acme", "agent-1", "ted")
    ted.last_scan_at = now - timedelta(minutes=30)
    await svc.sources.update(ted)
    monkeypatch.setattr(svc.ted, "search", lambda filters=None: _ted_notice())

    early = await scheduler.scan_due_sources(svc, now=now)
    assert early == {"active_sources": 1, "scanned": 0, "skipped": 1, "failed": 0}

    later = await scheduler.scan_due_sources(svc, now=now + timedelta(minutes=61))
    assert later["scanned"] == 1


async def test_scan_due_sources_manual_cadence_is_never_due(monkeypatch):
    """A 'manual' cadence source is never auto-scanned, even if it has never been scanned."""
    svc, _ = _build()
    await svc.update_source_status("acme", "agent-1", "ted", "active")
    await svc.update_source_cadence("acme", "agent-1", "ted", "manual")

    called = False

    def _search(filters=None):
        nonlocal called
        called = True
        return _ted_notice()

    monkeypatch.setattr(svc.ted, "search", _search)
    summary = await scheduler.scan_due_sources(svc, now=_now() + timedelta(days=7))

    assert summary == {"active_sources": 1, "scanned": 0, "skipped": 1, "failed": 0}
    assert called is False


# --- send_deadline_reminders ---
async def _add_opp(svc: OpportunityService, *, deadline_days: int, stage: str = "awaiting_review",
                   opp_id: str = "opp-1") -> Opportunity:
    opp = Opportunity(id=opp_id, tenant="acme", agent_id="agent-1", external_id=f"ext-{opp_id}",
                      source_key="ted", source_name="TED", title="Security tender", stage=stage,
                      deadline_at=_now() + timedelta(days=deadline_days))
    return await svc.opportunities.add(opp)


async def test_deadline_reminder_fires_once_for_approaching_opp():
    svc, inbox = _build()
    await _add_opp(svc, deadline_days=2)

    summary = await scheduler.send_deadline_reminders(svc, agents=svc.agents)

    assert summary["reminded"] == 1 and summary["considered"] == 1 and summary["deduped"] == 0
    assert len(_notifications_of_type(inbox, TYPE_DEADLINE_REMINDER)) == 1


async def test_deadline_reminder_not_sent_twice_same_day():
    svc, inbox = _build()
    await _add_opp(svc, deadline_days=2)

    first = await scheduler.send_deadline_reminders(svc, agents=svc.agents)
    second = await scheduler.send_deadline_reminders(svc, agents=svc.agents)

    assert first["reminded"] == 1
    assert second["reminded"] == 0 and second["deduped"] == 1
    assert len(_notifications_of_type(inbox, TYPE_DEADLINE_REMINDER)) == 1  # still only one


async def test_deadline_reminder_skips_far_off_and_terminal_and_no_deadline():
    svc, inbox = _build()
    await _add_opp(svc, deadline_days=30, opp_id="far")            # outside 3-day window
    await _add_opp(svc, deadline_days=1, stage="pushed", opp_id="terminal")  # terminal stage
    no_deadline = Opportunity(id="nd", tenant="acme", agent_id="agent-1", external_id="nd",
                              source_key="ted", source_name="TED", title="No deadline",
                              stage="qualified", deadline_at=None)
    await svc.opportunities.add(no_deadline)

    summary = await scheduler.send_deadline_reminders(svc, agents=svc.agents)

    assert summary["reminded"] == 0 and summary["considered"] == 0
    assert _notifications_of_type(inbox, TYPE_DEADLINE_REMINDER) == []


async def test_deadline_reminder_no_opportunities_is_clean():
    svc, _ = _build()
    summary = await scheduler.send_deadline_reminders(svc, agents=svc.agents)
    assert summary == {"with_deadline": 0, "considered": 0, "reminded": 0, "deduped": 0, "skipped": 0}


async def test_scan_due_sources_applies_saved_ingest_filter(monkeypatch):
    """REQ-5: the scheduled sweep applies the persisted per-agent ingest filter (saved keyword +
    allowlist bypasses), matching the manual scan path -- not an empty filter."""
    from app.modules.sales_intelligence.models import IngestFilterSetting, InMemoryIngestFilterSettingStore
    svc, _ = _build()
    await svc.update_source_status("acme", "agent-1", "ted", "active")
    captured: dict = {}

    def _search(filters=None):
        captured.update(filters or {})
        return _ted_notice()

    monkeypatch.setattr(svc.ted, "search", _search)
    store = InMemoryIngestFilterSettingStore()
    await store.update(IngestFilterSetting(tenant="acme", agent_id="agent-1", query_enabled=True,
                                           query_keyword="guarding", all_countries=True, all_categories=True))

    summary = await scheduler.scan_due_sources(svc, ingest_filters=store)

    assert summary["scanned"] == 1
    assert captured.get("query") == "guarding"
    assert captured.get("country_allowlist") == "*"
    assert captured.get("category_allowlist") == "*"
