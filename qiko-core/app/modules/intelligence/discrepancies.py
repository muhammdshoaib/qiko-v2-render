"""Correlate captured signals and surface discrepancy classes.

The engine never invents state: it reads the signal store and presents mismatches
between a human claim and a system-of-record fact. See the design spec in
`.devin/specs/2026-08-14-qiko-intelligence-worker-design.md`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


from app.modules.intelligence.models import Signal, SignalStore


DEFAULT_REVIEW_STALL = timedelta(hours=24)
DONE_STATUSES = {"DONE", "READY_TO_DEPLOY"}
TICKET_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]*-\d+)\b")
PR_REF_RE = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b")
BRANCH_REF_RE = re.compile(r"(?:feature|fix|chore)/([A-Za-z0-9]+-\d+)", re.IGNORECASE)

_COMPLETION_PHRASES = (
    "done", "finished", "completed", "complete", "shipped", "deployed",
    "released", "merged", "live", "published",
)
_CI_GREEN_PHRASES = (
    "ci green", "ci is green", "checks passed", "tests passed",
    "build passed", "all green", "green build", "pipeline green",
)
_NEGATORS = ("not", "no", "never", "didn't", "doesn't", "isn't", "wasn't")

_DISCREPANCY_LABELS: dict[str, dict[str, str]] = {
    "claimed_not_done": {"label": "Done claims not reflected", "severity": "high"},
    "done_without_evidence": {"label": "Done without linked work", "severity": "medium"},
    "stalled_review": {"label": "Stalled code review", "severity": "medium"},
    "blocked_and_silent": {"label": "Blocked and gone quiet", "severity": "high"},
    "ci_red_but_claimed_green": {"label": "Build claim mismatch", "severity": "high"},
    "discussed_never_tracked": {"label": "Discussed but not tracked", "severity": "low"},
}

_STATUS_LABELS: dict[str, str] = {
    "DONE": "done",
    "READY_TO_DEPLOY": "ready to deploy",
    "IN_PROGRESS": "in progress",
    "IN_REVIEW": "in review",
    "VERIFYING": "being verified",
    "BACKLOG": "in the backlog",
    "BLOCKED": "blocked",
}

_SOURCE_LABELS: dict[str, str] = {
    "qiko_track": "Qiko Track",
    "slack": "Slack",
    "github": "GitHub",
}


@dataclass(frozen=True)
class Discrepancy:
    """One mismatch between a claim and evidence, phrased for a non-technical reader."""

    discrepancy_class: str
    class_label: str
    severity: str
    ref: str | None
    title: str
    summary: str
    claimed_at: datetime | None
    evidence_at: datetime | None
    sources: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "class": self.discrepancy_class,
            "class_label": self.class_label,
            "severity": self.severity,
            "ref": self.ref,
            "title": self.title,
            "summary": self.summary,
            "claimed_at": _iso(self.claimed_at),
            "evidence_at": _iso(self.evidence_at),
            "sources": self.sources,
        }


def _class_meta(cls: str) -> dict[str, str]:
    return _DISCREPANCY_LABELS.get(cls, {"label": cls.replace("_", " "), "severity": "medium"})


def _status_label(status: str | None) -> str:
    if not status:
        return "not done"
    return _STATUS_LABELS.get(status.upper(), status.lower().replace("_", " "))


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source)


def _date(value: datetime | None) -> str:
    if value is None:
        return "unknown date"
    return value.strftime("%d %b %Y")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _extract_refs(text: str) -> list[str]:
    """Return normalised refs from a message, body or branch name."""
    refs: set[str] = set()
    if not text:
        return []
    for match in TICKET_KEY_RE.findall(text):
        refs.add(match.upper())
    for owner_repo, _number in PR_REF_RE.findall(text):
        # PR refs map to the same ticket key when one is present; leave repo-qualified
        # numbers as a fallback only.
        refs.add(f"{owner_repo}#{_number}")
    for match in BRANCH_REF_RE.findall(text):
        # Branch names are often lower-case: feature/qiw-1004-...
        refs.add(match.upper())
    return sorted(refs)


def _has_claim(text: str, phrases: tuple[str, ...]) -> bool:
    """True when `text` contains a positive claim from `phrases`."""
    text = (text or "").lower()
    for phrase in phrases:
        if phrase not in text:
            continue
        # Quick negation check: look at the words immediately before the phrase.
        idx = text.find(phrase)
        if idx == -1:
            continue
        before = text[:idx].strip().split()[-3:]
        if any(before_word in _NEGATORS for before_word in before):
            continue
        return True
    return False


def _latest_state(signals: list[Signal]) -> dict | None:
    """Return the most recent `meta.state` dict from Qiko Track signals."""
    latest: dict | None = None
    latest_at: datetime | None = None
    for signal in signals:
        if signal.source != "qiko_track":
            continue
        state = (signal.meta or {}).get("state")
        if isinstance(state, dict):
            if latest_at is None or signal.occurred_at > latest_at:
                latest_at = signal.occurred_at
                latest = state
    return latest


class DiscrepancyEngine:
    """Compute discrepancy classes from a worker's signal store."""

    def __init__(self, signal_store: SignalStore, *,
                 review_stall: timedelta | None = None) -> None:
        self.signal_store = signal_store
        self.review_stall = review_stall or DEFAULT_REVIEW_STALL

    async def analyze(self, tenant: str, agent_id: str, *,
                      since: datetime | None = None,
                      now: datetime | None = None) -> list[Discrepancy]:
        """Return all discrepancies visible for this worker."""
        now = now or datetime.now(timezone.utc)
        if since is None:
            since = now - timedelta(days=30)

        qt_signals = await self.signal_store.list_recent(
            tenant, agent_id, source="qiko_track", since=since, limit=10_000)
        slack_signals = await self.signal_store.list_recent(
            tenant, agent_id, source="slack", since=since, limit=10_000)
        github_signals = await self.signal_store.list_recent(
            tenant, agent_id, source="github", since=since, limit=10_000)

        by_ref: dict[str, dict[str, list[Signal]]] = {}

        def _bucket(signal: Signal) -> None:
            refs = [signal.ref] if signal.ref else _extract_refs(
                f"{signal.title or ''} {signal.body or ''}")
            for ref in refs:
                if not ref:
                    continue
                data = by_ref.setdefault(ref, {"qiko_track": [], "slack": [], "github": []})
                data[signal.source].append(signal)

        for s in qt_signals:
            _bucket(s)
        for s in slack_signals:
            _bucket(s)
        for s in github_signals:
            _bucket(s)

        results: list[Discrepancy] = []
        for ref, data in by_ref.items():
            results.extend(self._claimed_not_done(ref, data))
            results.extend(self._done_without_evidence(ref, data))
            results.extend(self._stalled_review(ref, data, now))
            results.extend(self._blocked_and_silent(ref, data))
            results.extend(self._ci_red_but_claimed_green(ref, data))

        results.extend(self._discussed_never_tracked(slack_signals, qt_signals))
        return sorted(results, key=lambda d: d.evidence_at or d.claimed_at or now, reverse=True)

    def _claimed_not_done(self, ref: str, data: dict[str, list[Signal]]) -> list[Discrepancy]:
        """Slack claims completion but ticket is not DONE/READY_TO_DEPLOY."""
        state = _latest_state(data["qiko_track"])
        if not state:
            return []
        status = state.get("status") or ""
        if status.upper() in DONE_STATUSES:
            return []

        for signal in data["slack"]:
            if _has_claim(signal.body, _COMPLETION_PHRASES):
                meta = _class_meta("claimed_not_done")
                return [Discrepancy(
                    discrepancy_class="claimed_not_done",
                    class_label=meta["label"],
                    severity=meta["severity"],
                    ref=ref,
                    title=f"Reported complete, still {_status_label(status)}",
                    summary=(
                        f"{ref} was reported complete in {signal.container} on "
                        f"{_date(signal.occurred_at)} by {signal.actor}, but Qiko Track "
                        f"still shows it as {_status_label(status)}."
                    ),
                    claimed_at=signal.occurred_at,
                    evidence_at=self._latest_time(data["qiko_track"]),
                    sources=self._sources([signal] + data["qiko_track"]),
                )]
        return []

    def _done_without_evidence(self, ref: str, data: dict[str, list[Signal]]) -> list[Discrepancy]:
        """Ticket is DONE but no merged PR references it."""
        state = _latest_state(data["qiko_track"])
        if not state or state.get("status", "").upper() not in DONE_STATUSES:
            return []
        merged = [s for s in data["github"] if s.kind in ("pr_merged", "commit")]
        if merged:
            return []
        latest = self._latest_signal(data["qiko_track"])
        meta = _class_meta("done_without_evidence")
        return [Discrepancy(
            discrepancy_class="done_without_evidence",
            class_label=meta["label"],
            severity=meta["severity"],
            ref=ref,
            title="Marked done with no linked code change",
            summary=(
                f"{ref} was marked done on {_date(latest.occurred_at)}, but no pull "
                "request or commit has been linked to it."
            ),
            claimed_at=None,
            evidence_at=latest.occurred_at,
            sources=self._sources(data["qiko_track"] + data["github"]),
        )]

    def _stalled_review(self, ref: str, data: dict[str, list[Signal]],
                        now: datetime) -> list[Discrepancy]:
        """PR open with review requested beyond the configured stall threshold."""
        requested = [s for s in data["github"] if s.kind == "review_requested"]
        if not requested:
            return []
        newest_requested = max(requested, key=lambda s: s.occurred_at)
        approved = [s for s in data["github"] if s.kind == "review_approved"]
        merged = [s for s in data["github"] if s.kind == "pr_merged"]
        if approved and max(a.occurred_at for a in approved) >= newest_requested.occurred_at:
            return []
        if merged and max(m.occurred_at for m in merged) >= newest_requested.occurred_at:
            return []
        if now - newest_requested.occurred_at < self.review_stall:
            return []
        meta = _class_meta("stalled_review")
        return [Discrepancy(
            discrepancy_class="stalled_review",
            class_label=meta["label"],
            severity=meta["severity"],
            ref=ref,
            title="Code review has been waiting too long",
            summary=(
                f"A review was requested for {ref} on {_date(newest_requested.occurred_at)} "
                "and has not been approved or merged since."
            ),
            claimed_at=None,
            evidence_at=newest_requested.occurred_at,
            sources=self._sources([newest_requested]),
        )]

    def _blocked_and_silent(self, ref: str, data: dict[str, list[Signal]]) -> list[Discrepancy]:
        """Ticket is blocked and no Slack activity has followed the block."""
        blocked_signals = [s for s in data["qiko_track"] if s.kind == "ticket_blocked"]
        if not blocked_signals:
            return []
        latest_block = max(blocked_signals, key=lambda s: s.occurred_at)
        meta = latest_block.meta or {}
        if not meta.get("blocked"):
            return []
        after = [s for s in data["slack"] if s.occurred_at > latest_block.occurred_at]
        if after:
            return []
        reason = meta.get("blocked_reason")
        reason_text = f": {reason}" if reason else ""
        meta = _class_meta("blocked_and_silent")
        return [Discrepancy(
            discrepancy_class="blocked_and_silent",
            class_label=meta["label"],
            severity=meta["severity"],
            ref=ref,
            title="Blocked work has had no follow-up",
            summary=(
                f"{ref} was blocked on {_date(latest_block.occurred_at)}{reason_text}. "
                "No one has discussed it since."
            ),
            claimed_at=None,
            evidence_at=latest_block.occurred_at,
            sources=self._sources([latest_block]),
        )]

    def _ci_red_but_claimed_green(self, ref: str, data: dict[str, list[Signal]]) -> list[Discrepancy]:
        """A Slack claim that CI is green contradicts a failed CI run."""
        failures = [s for s in data["github"] if s.kind == "ci_failed"]
        if not failures:
            return []
        latest_failure = max(failures, key=lambda s: s.occurred_at)
        for signal in data["slack"]:
            if not _has_claim(signal.body, _CI_GREEN_PHRASES):
                continue
            if signal.occurred_at > latest_failure.occurred_at:
                # Claim after the failure may be referring to a later fix.
                continue
            meta = _class_meta("ci_red_but_claimed_green")
            return [Discrepancy(
                discrepancy_class="ci_red_but_claimed_green",
                class_label=meta["label"],
                severity=meta["severity"],
                ref=ref,
                title="Build failure contradicted by a passing claim",
                summary=(
                    f"{signal.actor} said the build is passing on "
                    f"{_date(signal.occurred_at)}, but the latest recorded failed build for "
                    f"{ref} was on {_date(latest_failure.occurred_at)}."
                ),
                claimed_at=signal.occurred_at,
                evidence_at=latest_failure.occurred_at,
                sources=self._sources([signal, latest_failure]),
            )]
        return []

    def _discussed_never_tracked(self, slack_signals: list[Signal],
                                  qt_signals: list[Signal]) -> list[Discrepancy]:
        """Flagged Slack messages with no ref and no later Qiko Track ticket created."""
        qt_created = [s for s in qt_signals if s.kind == "ticket_created"]
        results: list[Discrepancy] = []
        for signal in slack_signals:
            if signal.ref:
                continue
            if not signal.flagged and not any(
                tag in ("action", "feature", "important") for tag in (signal.tags or [])
            ):
                continue
            after = [s for s in qt_created if s.occurred_at > signal.occurred_at]
            if after:
                continue
            meta = _class_meta("discussed_never_tracked")
            results.append(Discrepancy(
                discrepancy_class="discussed_never_tracked",
                class_label=meta["label"],
                severity=meta["severity"],
                ref=None,
                title="Important Slack message never became a ticket",
                summary=(
                    f"A flagged message in {signal.container} on "
                    f"{_date(signal.occurred_at)} has no ticket reference and no "
                    "follow-up ticket was created."
                ),
                claimed_at=signal.occurred_at,
                evidence_at=None,
                sources=self._sources([signal]),
            ))
        return results

    def _latest_signal(self, signals: list[Signal]) -> Signal:
        return max(signals, key=lambda s: s.occurred_at)

    def _latest_time(self, signals: list[Signal]) -> datetime | None:
        if not signals:
            return None
        return self._latest_signal(signals).occurred_at

    def _sources(self, signals: list[Signal]) -> list[dict]:
        seen: set[str] = set()
        sources: list[dict] = []
        for s in signals:
            key = f"{s.source}:{s.external_id}"
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                "source": s.source,
                "source_label": _source_label(s.source),
                "external_id": s.external_id,
                "url": s.url,
                "actor": s.actor,
                "occurred_at": _iso(s.occurred_at),
            })
        return sources
