import pytest
from datetime import datetime, timedelta, timezone

from app.modules.intelligence.models import InMemorySignalStore, Signal
from app.modules.intelligence.discrepancies import DiscrepancyEngine


T0 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def _signal(**overrides) -> Signal:
    base = dict(
        tenant="t1", agent_id="w1", source="slack", kind="message",
        external_id="ev-1", container="T1/C1", actor="U1",
        title="title", body="body", occurred_at=T0,
        ref=None, url=None, tags=[], flagged=False, meta={},
    )
    base.update(overrides)
    return Signal(**base)


@pytest.fixture
def store():
    return InMemorySignalStore()


@pytest.fixture
def engine(store):
    return DiscrepancyEngine(store)


@pytest.mark.asyncio
async def test_claimed_not_done(store, engine):
    await store.add(_signal(
        source="slack", external_id="s1", body="QIW-1004 is done",
        title="QIW-1004 is done", ref="QIW-1004"))
    await store.add(_signal(
        source="qiko_track", kind="ticket_moved", external_id="qt1",
        ref="QIW-1004", meta={"state": {"status": "IN_PROGRESS"}}))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert len(result) == 1
    assert result[0].discrepancy_class == "claimed_not_done"
    assert result[0].ref == "QIW-1004"


@pytest.mark.asyncio
async def test_no_claimed_not_done_when_done(store, engine):
    await store.add(_signal(
        source="slack", external_id="s1", body="QIW-1004 is done",
        ref="QIW-1004"))
    await store.add(_signal(
        source="qiko_track", kind="ticket_moved", external_id="qt1",
        ref="QIW-1004", meta={"state": {"status": "DONE"}}))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert all(d.discrepancy_class != "claimed_not_done" for d in result)


@pytest.mark.asyncio
async def test_done_without_evidence(store, engine):
    await store.add(_signal(
        source="qiko_track", kind="ticket_moved", external_id="qt1",
        ref="QIW-1004", meta={"state": {"status": "DONE"}}))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert len(result) == 1
    assert result[0].discrepancy_class == "done_without_evidence"


@pytest.mark.asyncio
async def test_done_with_pr_evidence(store, engine):
    await store.add(_signal(
        source="qiko_track", kind="ticket_moved", external_id="qt1",
        ref="QIW-1004", meta={"state": {"status": "DONE"}}))
    await store.add(_signal(
        source="github", kind="pr_merged", external_id="gh1",
        ref="QIW-1004"))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert result == []


@pytest.mark.asyncio
async def test_blocked_and_silent(store, engine):
    await store.add(_signal(
        source="qiko_track", kind="ticket_blocked", external_id="qt1",
        ref="QIW-1004", meta={"blocked": True, "state": {"blocked": True}}))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert len(result) == 1
    assert result[0].discrepancy_class == "blocked_and_silent"


@pytest.mark.asyncio
async def test_blocked_with_slack_followup(store, engine):
    await store.add(_signal(
        source="qiko_track", kind="ticket_blocked", external_id="qt1",
        ref="QIW-1004", occurred_at=T0,
        meta={"blocked": True, "state": {"blocked": True}}))
    await store.add(_signal(
        source="slack", external_id="s1", body="unblocking", ref="QIW-1004",
        occurred_at=T0 + timedelta(minutes=5)))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert result == []


@pytest.mark.asyncio
async def test_discussed_never_tracked(store, engine):
    await store.add(_signal(
        source="slack", external_id="s1", body="we need to fix pricing",
        title="we need to fix pricing", flagged=True))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert len(result) == 1
    assert result[0].discrepancy_class == "discussed_never_tracked"
    assert result[0].ref is None


@pytest.mark.asyncio
async def test_stalled_review(store, engine):
    await store.add(_signal(
        source="github", kind="review_requested", external_id="gh1",
        ref="QIW-1004", occurred_at=T0))

    result = await engine.analyze(
        "t1", "w1", now=T0 + timedelta(hours=25), since=T0 - timedelta(days=1))

    assert len(result) == 1
    assert result[0].discrepancy_class == "stalled_review"


@pytest.mark.asyncio
async def test_ci_red_but_claimed_green(store, engine):
    await store.add(_signal(
        source="slack", external_id="s1", body="CI is green for QIW-1004",
        ref="QIW-1004"))
    await store.add(_signal(
        source="github", kind="ci_failed", external_id="gh1",
        ref="QIW-1004", occurred_at=T0 + timedelta(hours=1)))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=2))

    assert len(result) == 1
    assert result[0].discrepancy_class == "ci_red_but_claimed_green"


@pytest.mark.asyncio
async def test_project_key_extracted_from_ref(store, engine):
    await store.add(_signal(
        source="slack", external_id="s1", body="QIW-1004 is done",
        title="QIW-1004 is done", ref="QIW-1004"))
    await store.add(_signal(
        source="qiko_track", kind="ticket_moved", external_id="qt1",
        ref="QIW-1004", meta={"state": {"status": "IN_PROGRESS"}}))

    result = await engine.analyze("t1", "w1", now=T0 + timedelta(hours=1))

    assert result[0].project_key == "QIW"


@pytest.mark.asyncio
async def test_analyze_paginated_returns_total_and_counts(store, engine):
    for i in range(5):
        await store.add(_signal(
            source="qiko_track", kind="ticket_moved", external_id=f"qt{i}",
            ref=f"QIW-{1000 + i}", occurred_at=T0 + timedelta(hours=i),
            meta={"state": {"status": "DONE"}}))

    items, total, counts = await engine.analyze_paginated("t1", "w1", limit=2, offset=0)

    assert total == 5
    assert len(items) == 2
    assert counts["QIW"] == 5


@pytest.mark.asyncio
async def test_project_filter_excludes_other_projects(store, engine):
    await store.add(_signal(
        source="qiko_track", kind="ticket_moved", external_id="qt1",
        ref="ABC-1", occurred_at=T0,
        meta={"state": {"status": "DONE"}}))
    await store.add(_signal(
        source="qiko_track", kind="ticket_moved", external_id="qt2",
        ref="QIW-1004", occurred_at=T0,
        meta={"state": {"status": "DONE"}}))

    result = await engine.analyze("t1", "w1", project_keys={"QIW"})

    assert len(result) == 1
    assert result[0].ref == "QIW-1004"
