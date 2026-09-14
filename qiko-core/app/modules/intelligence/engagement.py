"""Conversation engagement: who's active, and who has an unanswered mention waiting on them.

Deterministic reconstruction from already-ingested Slack Signals - the same discipline every
discrepancy class in discrepancies.py and the overview aggregation in overview.py already
follow. This reports "mentioned, no reply yet, N hours" as a fact, never a judgment about why -
someone may be on leave, may not be the right person, or the message may not have needed a
reply. A human triages this list; nothing here decides anything on its own.

See .devin/plans/2026-09-14-qiw-1024-engagement.md for the judgment calls this makes (Slack
only for v1, Role.admin, a separate tab) - override any of them freely, they were not put to a
design round-trip before this was built.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.modules.intelligence.models import Signal

_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _thread_key(signal: Signal) -> str:
    """Group a Slack signal into its conversation: the thread it replied in, or its own
    timestamp if it started one (or never became a thread at all)."""
    thread_ts = (signal.meta or {}).get("thread_ts")
    return thread_ts or signal.external_id


def _active(signals: list[Signal]) -> list[dict]:
    counts: dict[str, dict] = {}
    for signal in signals:
        row = counts.setdefault(signal.actor, {"actor": signal.actor, "message_count": 0,
                                                "channels": set()})
        row["message_count"] += 1
        row["channels"].add(signal.container)
    rows = [{"actor": r["actor"], "message_count": r["message_count"],
            "channels": sorted(r["channels"])} for r in counts.values()]
    rows.sort(key=lambda r: r["message_count"], reverse=True)
    return rows


def _awaiting_response(signals: list[Signal], now: datetime, threshold_hours: float) -> list[dict]:
    groups: dict[tuple[str, str], list[Signal]] = {}
    for signal in signals:
        key = (signal.container, _thread_key(signal))
        groups.setdefault(key, []).append(signal)
    for group in groups.values():
        group.sort(key=lambda s: _as_utc(s.occurred_at))

    rows: list[dict] = []
    for (container, _key), group in groups.items():
        for signal in group:
            mentioned_ids = set(_MENTION_RE.findall(signal.body or ""))
            for mentioned in mentioned_ids:
                if mentioned == signal.actor:
                    continue
                replied = any(
                    other.actor == mentioned and _as_utc(other.occurred_at) > _as_utc(signal.occurred_at)
                    for other in group)
                if replied:
                    continue
                hours_waiting = (now - _as_utc(signal.occurred_at)).total_seconds() / 3600
                if hours_waiting < threshold_hours:
                    continue
                rows.append({
                    "mentioned": mentioned, "mentioned_by": signal.actor,
                    "container": container, "since": signal.occurred_at.isoformat(),
                    "hours_waiting": round(hours_waiting, 1), "url": signal.url,
                })
    rows.sort(key=lambda r: r["hours_waiting"], reverse=True)
    return rows


def build_engagement(signals: list[Signal], *, now: datetime | None = None,
                     awaiting_threshold_hours: float = 24.0) -> dict:
    now = now or datetime.now(timezone.utc)
    slack_signals = [s for s in signals if s.source == "slack"]
    return {
        "active": _active(slack_signals),
        "awaiting_response": _awaiting_response(slack_signals, now, awaiting_threshold_hours),
    }
