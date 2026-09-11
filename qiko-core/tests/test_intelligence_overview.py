from datetime import datetime, timedelta, timezone

from app.modules.intelligence.models import Signal
from app.modules.intelligence.overview import build_overview


def _signal(kind, ref, actor="dev1", container="acme/repo", occurred_at=None,
           source="github", meta=None, title="t"):
    return Signal(
        tenant="acme", agent_id="a1", source=source, kind=kind,
        external_id=f"{kind}-{ref}", container=container, actor=actor, title=title,
        body="", occurred_at=occurred_at or datetime.now(timezone.utc), ref=ref,
        meta=meta or {})


def test_a_pr_with_no_merge_or_close_signal_is_open():
    now = datetime.now(timezone.utc)
    signals = [_signal("pr_opened", "PR#42", actor="alice", occurred_at=now - timedelta(hours=5))]
    result = build_overview(signals, now=now)
    assert len(result["open_prs"]) == 1
    pr = result["open_prs"][0]
    assert pr["ref"] == "PR#42"
    assert pr["author"] == "alice"
    assert pr["age_hours"] == 5


def test_a_pr_with_a_later_merge_signal_is_not_open():
    now = datetime.now(timezone.utc)
    signals = [
        _signal("pr_opened", "PR#42", actor="alice", occurred_at=now - timedelta(hours=5)),
        _signal("pr_merged", "PR#42", actor="alice", occurred_at=now - timedelta(hours=1)),
    ]
    result = build_overview(signals, now=now)
    assert result["open_prs"] == []


def test_an_open_pr_with_a_review_request_reports_review_status():
    now = datetime.now(timezone.utc)
    signals = [
        _signal("pr_opened", "PR#7", actor="bob", occurred_at=now - timedelta(hours=10)),
        _signal("review_requested", "PR#7", actor="bob", occurred_at=now - timedelta(hours=9)),
    ]
    result = build_overview(signals, now=now)
    assert result["open_prs"][0]["review_status"] == "review_requested"


def test_an_open_pr_with_an_approval_reports_approved():
    now = datetime.now(timezone.utc)
    signals = [
        _signal("pr_opened", "PR#7", actor="bob", occurred_at=now - timedelta(hours=10)),
        _signal("review_requested", "PR#7", actor="bob", occurred_at=now - timedelta(hours=9)),
        _signal("review_approved", "PR#7", actor="carol", occurred_at=now - timedelta(hours=2)),
    ]
    result = build_overview(signals, now=now)
    assert result["open_prs"][0]["review_status"] == "review_approved"


def test_a_ticket_moved_to_in_progress_appears_in_the_overview():
    now = datetime.now(timezone.utc)
    signals = [_signal("ticket_moved", "QIW-1", actor="dave", source="qiko_track",
                       occurred_at=now - timedelta(hours=1),
                       meta={"state": {"status": "IN_PROGRESS", "implementer": "dave"}})]
    result = build_overview(signals, now=now)
    assert len(result["in_progress_tickets"]) == 1
    ticket = result["in_progress_tickets"][0]
    assert ticket["ref"] == "QIW-1"
    assert ticket["status"] == "IN_PROGRESS"


def test_a_ticket_later_moved_to_done_is_not_in_progress():
    now = datetime.now(timezone.utc)
    signals = [
        _signal("ticket_moved", "QIW-1", actor="dave", source="qiko_track",
               occurred_at=now - timedelta(hours=5),
               meta={"state": {"status": "IN_PROGRESS", "implementer": "dave"}}),
        _signal("ticket_moved", "QIW-1", actor="dave", source="qiko_track",
               occurred_at=now - timedelta(hours=1),
               meta={"state": {"status": "DONE", "implementer": "dave"}}),
    ]
    result = build_overview(signals, now=now)
    assert result["in_progress_tickets"] == []


def test_in_progress_ticket_derives_project_key_from_ref_and_actor_from_implementer():
    now = datetime.now(timezone.utc)
    signals = [_signal("ticket_moved", "QIW-1023", actor="mover-bot", source="qiko_track",
                       occurred_at=now - timedelta(hours=1),
                       meta={"state": {"status": "IN_REVIEW", "implementer": "dave"}})]
    result = build_overview(signals, now=now)
    ticket = result["in_progress_tickets"][0]
    assert ticket["project_key"] == "QIW"
    assert ticket["actor"] == "dave"


def test_in_progress_ticket_falls_back_to_mover_when_no_implementer_recorded():
    now = datetime.now(timezone.utc)
    signals = [_signal("ticket_moved", "QIW-1023", actor="mover-bot", source="qiko_track",
                       occurred_at=now - timedelta(hours=1),
                       meta={"state": {"status": "IN_PROGRESS", "implementer": ""}})]
    result = build_overview(signals, now=now)
    ticket = result["in_progress_tickets"][0]
    assert ticket["actor"] == "mover-bot"


def test_in_progress_ticket_uses_a_later_ticket_assigned_signal_over_an_earlier_ticket_moved():
    # ticket_assigned fires when only the implementer changes, with no status change, and
    # carries its own full meta.state snapshot. It must win over an earlier ticket_moved
    # for the same ref, not just be ignored because its kind isn't "ticket_moved".
    now = datetime.now(timezone.utc)
    signals = [
        _signal("ticket_moved", "QIW-1", actor="dave", source="qiko_track",
               occurred_at=now - timedelta(hours=5),
               meta={"state": {"status": "IN_PROGRESS", "implementer": ""}}),
        _signal("ticket_assigned", "QIW-1", actor="mover-bot", source="qiko_track",
               occurred_at=now - timedelta(hours=1),
               meta={"state": {"status": "IN_PROGRESS", "implementer": "erin"}}),
    ]
    result = build_overview(signals, now=now)
    assert len(result["in_progress_tickets"]) == 1
    ticket = result["in_progress_tickets"][0]
    assert ticket["actor"] == "erin"


def test_in_progress_ticket_picks_the_chronologically_latest_state_when_input_is_out_of_order():
    # Signals arrive in whatever order the store returns them; the grouping must sort by
    # occurred_at itself rather than trusting input order.
    now = datetime.now(timezone.utc)
    signals = [
        _signal("ticket_assigned", "QIW-1", actor="mover-bot", source="qiko_track",
               occurred_at=now - timedelta(hours=1),
               meta={"state": {"status": "IN_PROGRESS", "implementer": "erin"}}),
        _signal("ticket_moved", "QIW-1", actor="dave", source="qiko_track",
               occurred_at=now - timedelta(hours=5),
               meta={"state": {"status": "IN_PROGRESS", "implementer": ""}}),
        _signal("ticket_moved", "QIW-1", actor="dave", source="qiko_track",
               occurred_at=now - timedelta(hours=3),
               meta={"state": {"status": "IN_REVIEW", "implementer": "dave"}}),
    ]
    result = build_overview(signals, now=now)
    assert len(result["in_progress_tickets"]) == 1
    ticket = result["in_progress_tickets"][0]
    assert ticket["status"] == "IN_PROGRESS"
    assert ticket["actor"] == "erin"


def test_open_pr_excludes_a_ref_with_a_terminal_signal_regardless_of_review_signal_count():
    now = datetime.now(timezone.utc)
    signals = [
        _signal("pr_opened", "PR#9", actor="bob", occurred_at=now - timedelta(hours=20)),
        _signal("review_requested", "PR#9", actor="bob", occurred_at=now - timedelta(hours=18)),
        _signal("review_changes_requested", "PR#9", actor="carol",
               occurred_at=now - timedelta(hours=15)),
        _signal("review_requested", "PR#9", actor="bob", occurred_at=now - timedelta(hours=10)),
        _signal("review_approved", "PR#9", actor="carol", occurred_at=now - timedelta(hours=5)),
        _signal("pr_merged", "PR#9", actor="bob", occurred_at=now - timedelta(hours=1)),
    ]
    result = build_overview(signals, now=now)
    assert result["open_prs"] == []


def test_developer_rollup_counts_open_prs_and_in_progress_tickets_per_actor():
    now = datetime.now(timezone.utc)
    signals = [
        _signal("pr_opened", "PR#1", actor="alice", occurred_at=now - timedelta(hours=1)),
        _signal("pr_opened", "PR#2", actor="alice", occurred_at=now - timedelta(hours=2)),
        _signal("ticket_moved", "QIW-1", actor="alice", source="qiko_track",
               occurred_at=now - timedelta(hours=1),
               meta={"state": {"status": "IN_PROGRESS", "implementer": "alice"}}),
        _signal("pr_opened", "PR#3", actor="bob", occurred_at=now - timedelta(hours=3)),
    ]
    result = build_overview(signals, now=now)
    by_actor = {d["actor"]: d for d in result["developers"]}
    assert by_actor["alice"]["open_prs"] == 2
    assert by_actor["alice"]["in_progress_tickets"] == 1
    assert by_actor["bob"]["open_prs"] == 1
    assert by_actor["bob"]["in_progress_tickets"] == 0
