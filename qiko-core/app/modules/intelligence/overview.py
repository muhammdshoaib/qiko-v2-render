"""Dashboard overview: open PRs, in-progress tickets, and a per-developer roll-up.

Deterministic reconstruction from already-ingested Signals, the same discipline every
discrepancy class in discrepancies.py already follows: never let a model decide "is this PR
open" or "who is busy" - compute it in Python from the signal store, so every number in the
dashboard is exactly re-derivable from the underlying event log.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.modules.intelligence.models import Signal

# A PR's terminal kinds. If the LATEST github signal for a ref is one of these, the PR is closed.
_PR_TERMINAL_KINDS = frozenset({"pr_merged", "pr_closed"})
_PR_REVIEW_KINDS = frozenset({"review_requested", "review_approved", "review_changes_requested"})
_IN_PROGRESS_STATUSES = frozenset({"IN_PROGRESS", "IN_REVIEW"})


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _group_by_ref(signals: list[Signal], *, source: str) -> dict[str, list[Signal]]:
    groups: dict[str, list[Signal]] = {}
    for signal in signals:
        if signal.source != source or not signal.ref:
            continue
        groups.setdefault(signal.ref, []).append(signal)
    for group in groups.values():
        group.sort(key=lambda s: _as_utc(s.occurred_at))
    return groups


def _open_prs(signals: list[Signal], now: datetime) -> list[dict]:
    groups = _group_by_ref(signals, source="github")
    open_prs = []
    for ref, group in groups.items():
        if not any(s.kind == "pr_opened" for s in group):
            continue
        if any(s.kind in _PR_TERMINAL_KINDS for s in group):
            continue
        opened = next(s for s in group if s.kind == "pr_opened")
        review_signals = [s for s in group if s.kind in _PR_REVIEW_KINDS]
        review_status = review_signals[-1].kind if review_signals else None
        age_hours = round((now - _as_utc(opened.occurred_at)).total_seconds() / 3600, 1)
        open_prs.append({
            "ref": ref, "container": opened.container, "author": opened.actor,
            "title": opened.title, "url": opened.url, "age_hours": age_hours,
            "review_status": review_status,
        })
    open_prs.sort(key=lambda p: p["age_hours"], reverse=True)
    return open_prs


def _project_key(ref: str) -> str | None:
    """A ticket ref always has the shape `PROJECT-123` in this codebase."""
    if "-" not in ref:
        return None
    return ref.split("-")[0]


def _in_progress_tickets(signals: list[Signal]) -> list[dict]:
    groups = _group_by_ref(signals, source="qiko_track")
    tickets = []
    for ref, group in groups.items():
        moves = [s for s in group
                 if s.kind == "ticket_moved" and isinstance((s.meta or {}).get("state"), dict)]
        if not moves:
            continue
        latest = moves[-1]
        state = (latest.meta or {}).get("state", {})
        status = state.get("status")
        if status not in _IN_PROGRESS_STATUSES:
            continue
        # The implementer is the ticket's real owner; the mover may just be an automated
        # sync or someone doing unrelated triage. Fall back to the mover when unassigned.
        actor = state.get("implementer") or latest.actor
        tickets.append({
            "ref": ref, "status": status, "actor": actor,
            "project_key": _project_key(ref),
            "url": latest.url, "updated_at": latest.occurred_at.isoformat(),
        })
    return tickets


def _developer_rollup(open_prs: list[dict], in_progress_tickets: list[dict]) -> list[dict]:
    counts: dict[str, dict[str, int]] = {}
    for pr in open_prs:
        counts.setdefault(pr["author"], {"open_prs": 0, "in_progress_tickets": 0})
        counts[pr["author"]]["open_prs"] += 1
    for ticket in in_progress_tickets:
        actor = ticket["actor"]
        counts.setdefault(actor, {"open_prs": 0, "in_progress_tickets": 0})
        counts[actor]["in_progress_tickets"] += 1
    developers = [{"actor": actor, **c} for actor, c in counts.items()]
    developers.sort(key=lambda d: d["open_prs"] + d["in_progress_tickets"], reverse=True)
    return developers


def build_overview(signals: list[Signal], *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    open_prs = _open_prs(signals, now)
    in_progress_tickets = _in_progress_tickets(signals)
    return {
        "open_prs": open_prs,
        "in_progress_tickets": in_progress_tickets,
        "developers": _developer_rollup(open_prs, in_progress_tickets),
    }
