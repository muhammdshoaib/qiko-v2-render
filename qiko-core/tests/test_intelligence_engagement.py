from datetime import datetime, timedelta, timezone

from app.modules.intelligence.models import Signal
from app.modules.intelligence.engagement import build_engagement


def _slack_signal(actor, text, *, container="T1/C1", occurred_at=None, thread_ts=None,
                  external_id=None):
    now = occurred_at or datetime.now(timezone.utc)
    return Signal(
        tenant="acme", agent_id="a1", source="slack", kind="message",
        external_id=external_id or f"{now.timestamp():.6f}",
        container=container, actor=actor, title=text[:50], body=text,
        occurred_at=now, url=f"https://slack.example/{container}",
        meta={"thread_ts": thread_ts})


def test_active_counts_messages_per_actor():
    now = datetime.now(timezone.utc)
    signals = [
        _slack_signal("UALICE", "morning", occurred_at=now - timedelta(hours=2)),
        _slack_signal("UALICE", "another one", occurred_at=now - timedelta(hours=1)),
        _slack_signal("UBOB", "hey", occurred_at=now - timedelta(hours=3)),
    ]
    result = build_engagement(signals, now=now)
    by_actor = {row["actor"]: row for row in result["active"]}
    assert by_actor["UALICE"]["message_count"] == 2
    assert by_actor["UBOB"]["message_count"] == 1


def test_active_is_sorted_by_message_count_descending():
    now = datetime.now(timezone.utc)
    signals = [
        _slack_signal("UBOB", "one"),
        _slack_signal("UALICE", "one"), _slack_signal("UALICE", "two"),
    ]
    result = build_engagement(signals, now=now)
    assert [row["actor"] for row in result["active"]] == ["UALICE", "UBOB"]


def test_a_mention_with_no_reply_from_the_mentioned_user_is_awaiting_response():
    now = datetime.now(timezone.utc)
    signals = [
        _slack_signal("UALICE", "hey <@UBOB> can you check this", thread_ts=None,
                     occurred_at=now - timedelta(hours=30), external_id="1000.0001"),
    ]
    result = build_engagement(signals, now=now)
    assert len(result["awaiting_response"]) == 1
    row = result["awaiting_response"][0]
    assert row["mentioned"] == "UBOB"
    assert row["mentioned_by"] == "UALICE"
    assert row["hours_waiting"] >= 29


def test_a_reply_from_the_mentioned_user_in_the_same_thread_clears_it():
    now = datetime.now(timezone.utc)
    signals = [
        _slack_signal("UALICE", "hey <@UBOB> can you check this", thread_ts=None,
                     occurred_at=now - timedelta(hours=30), external_id="1000.0001"),
        _slack_signal("UBOB", "on it", thread_ts="1000.0001",
                     occurred_at=now - timedelta(hours=20), external_id="1000.0002"),
    ]
    result = build_engagement(signals, now=now)
    assert result["awaiting_response"] == []


def test_a_mention_younger_than_the_threshold_is_not_yet_flagged():
    now = datetime.now(timezone.utc)
    signals = [
        _slack_signal("UALICE", "hey <@UBOB> quick one", thread_ts=None,
                     occurred_at=now - timedelta(hours=2), external_id="1000.0003"),
    ]
    result = build_engagement(signals, now=now)
    assert result["awaiting_response"] == []


def test_a_reply_in_a_different_thread_does_not_clear_the_mention():
    now = datetime.now(timezone.utc)
    signals = [
        _slack_signal("UALICE", "hey <@UBOB> can you check this", thread_ts=None,
                     occurred_at=now - timedelta(hours=30), external_id="1000.0001"),
        _slack_signal("UBOB", "unrelated message", thread_ts=None,
                     occurred_at=now - timedelta(hours=10), external_id="2000.0001"),
    ]
    result = build_engagement(signals, now=now)
    assert len(result["awaiting_response"]) == 1


def test_a_self_mention_is_never_flagged_as_awaiting_a_reply():
    now = datetime.now(timezone.utc)
    signals = [
        _slack_signal("UALICE", "note to self <@UALICE> follow up on this", thread_ts=None,
                     occurred_at=now - timedelta(hours=30), external_id="1000.0004"),
    ]
    result = build_engagement(signals, now=now)
    assert result["awaiting_response"] == []
