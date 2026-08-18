"""History strategies for the Qiko Track connector.

`PollAndDiff` is the current implementation: it fetches current ticket state and emits one Signal per
observed change. A future `BulkActivityFeed` can implement the same `HistoryStrategy` protocol and
replace it without changing `QikoTrackConnector` or its callers.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from app.modules.intelligence.models import Signal, SignalStore
from app.modules.intelligence.qiko_track_client import QikoTrackClient, QikoTrackClientError


class HistoryStrategy(Protocol):
    """How a Qiko Track connector turns API responses into a stream of Signals."""

    async def fetch(self, *, base_url: str, token: str, project_keys: list[str],
                    tenant: str, agent_id: str, signal_store: SignalStore,
                    since: datetime, transport: Any | None = None,
                    resolver: Any | None = None) -> list[Signal]: ...


@dataclass
class PollAndDiff:
    """Poll current ticket state and emit a Signal for each observed change.

    This loses intermediate hops between sweeps (a known limitation documented in QIW-1005),
    but emits one distinct Signal per changed field and is idempotent on re-read.
    """

    async def fetch(self, *, base_url: str, token: str, project_keys: list[str],
                    tenant: str, agent_id: str, signal_store: SignalStore,
                    since: datetime, transport: Any | None = None,
                    resolver: Any | None = None) -> list[Signal]:
        if not project_keys:
            return []

        client = QikoTrackClient(base_url, token, transport=transport, resolver=resolver)
        try:
            tickets = await client.list_tickets()
        except QikoTrackClientError:
            return []

        project_set = set(project_keys)
        filtered = [t for t in tickets if (t.get("project") or "") in project_set]

        signals: list[Signal] = []
        for ticket in filtered:
            signals.extend(await self._process_ticket(
                client, tenant, agent_id, base_url, since, signal_store, ticket))
        return signals

    async def _process_ticket(self, client: QikoTrackClient, tenant: str, agent_id: str,
                              base_url: str, since: datetime, signal_store: SignalStore,
                              ticket: dict) -> list[Signal]:
        key = ticket.get("key") or ""
        project = ticket.get("project") or ""
        if not key or not project:
            return []

        previous = await self._previous_state(signal_store, tenant, agent_id, key)
        current_compact = self._compact_state(ticket)

        needs_detail = previous is None or self._state_changed(previous, current_compact)
        if not needs_detail:
            return []

        try:
            detail = await client.get_ticket(key)
        except QikoTrackClientError:
            detail = ticket

        created_at = self._parse_time(detail.get("createdAt")) or datetime.now(timezone.utc)
        updated_at = self._parse_time(detail.get("updatedAt")) or created_at

        if previous is None:
            return [self._created_signal(tenant, agent_id, base_url, project, detail,
                                         created_at=created_at)]

        current = self._full_state(detail)
        return self._diff_signals(tenant, agent_id, base_url, project, key,
                                  previous, current, detail, updated_at, since)

    async def _previous_state(self, signal_store: SignalStore, tenant: str, agent_id: str,
                              key: str) -> dict | None:
        signals = await signal_store.list_recent(
            tenant, agent_id, source="qiko_track", ref=key, limit=10000)
        state: dict | None = None
        for signal in signals:
            signal_state = (signal.meta or {}).get("state")
            if isinstance(signal_state, dict):
                state = signal_state
        return state

    @staticmethod
    def _compact_state(ticket: dict) -> dict:
        """The subset of a list-ticket row we can compare before fetching detail."""
        return {
            "status": ticket.get("status") or "",
            "blocked": bool(ticket.get("isBlocked")),
            "blocked_reason": ticket.get("blockedReason") or "",
            "implementer": ticket.get("implementer") or "",
            "comments": int(ticket.get("comments") or 0),
        }

    @staticmethod
    def _full_state(detail: dict) -> dict:
        return {
            "status": detail.get("status") or "",
            "blocked": bool(detail.get("isBlocked")),
            "blocked_reason": detail.get("blockedReason") or "",
            "implementer": detail.get("implementer") or "",
            "comments": len(detail.get("comments") or []),
        }

    @staticmethod
    def _state_changed(previous: dict, current: dict) -> bool:
        return (
            previous.get("status") != current.get("status")
            or previous.get("blocked") != current.get("blocked")
            or previous.get("implementer") != current.get("implementer")
            or previous.get("comments") != current.get("comments")
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    def _created_signal(self, tenant: str, agent_id: str, base_url: str, project: str,
                        detail: dict, created_at: datetime) -> Signal:
        key = detail.get("key") or ""
        title = detail.get("title") or ""
        status = detail.get("status") or ""
        reporter = detail.get("reporter") or ""
        blocked = bool(detail.get("isBlocked"))
        blocked_reason = detail.get("blockedReason") or ""
        state = self._full_state(detail)
        state["title"] = title
        state["description"] = (detail.get("description") or "")[:200]

        return Signal(
            tenant=tenant,
            agent_id=agent_id,
            source="qiko_track",
            kind="ticket_created",
            external_id=f"{project}:{key}:created:{created_at.isoformat()}",
            container=project,
            actor=reporter,
            title=f"{key} created",
            body=f"Ticket {key} was created with status {status} in {project}.",
            occurred_at=created_at,
            ref=key,
            url=f"{base_url}/tickets/{key}",
            tags=list(detail.get("labels") or []),
            flagged=blocked,
            meta={
                "state": state,
                "priority": detail.get("priority") or "",
                "type": detail.get("type") or "",
                "blocked_reason": blocked_reason,
            },
        )

    def _diff_signals(self, tenant: str, agent_id: str, base_url: str, project: str,
                      key: str, previous: dict, current: dict, detail: dict,
                      updated_at: datetime, since: datetime) -> list[Signal]:
        activity = detail.get("activity") or []
        comments = detail.get("comments") or []
        title = detail.get("title") or ""
        state = self._full_state(detail)
        state["title"] = title
        state["description"] = (detail.get("description") or "")[:200]

        signals: list[Signal] = []
        if previous.get("status") != current.get("status"):
            actor, at = self._find_activity(activity, "status", current.get("status"), updated_at)
            from_status = previous.get("status") or ""
            to_status = current.get("status") or ""
            signals.append(Signal(
                tenant=tenant, agent_id=agent_id, source="qiko_track",
                kind="ticket_moved",
                external_id=f"{project}:{key}:moved:{from_status}:{to_status}:{at.isoformat()}",
                container=project, actor=actor or "",
                title=f"{key} moved to {to_status}",
                body=f"Ticket {key} moved from {from_status} to {to_status}.",
                occurred_at=at, ref=key, url=f"{base_url}/tickets/{key}",
                tags=list(detail.get("labels") or []),
                flagged=current.get("blocked") or False,
                meta={
                    "state": state,
                    "from_status": from_status,
                    "to_status": to_status,
                },
            ))

        if previous.get("blocked") != current.get("blocked"):
            actor, at = self._find_activity(activity, "blocked",
                                            "true" if current.get("blocked") else "false",
                                            updated_at)
            blocked = bool(current.get("blocked"))
            blocked_reason = current.get("blocked_reason") or ""
            signals.append(Signal(
                tenant=tenant, agent_id=agent_id, source="qiko_track",
                kind="ticket_blocked",
                external_id=f"{project}:{key}:blocked:{blocked}:{at.isoformat()}",
                container=project, actor=actor or "",
                title=f"{key} {'blocked' if blocked else 'unblocked'}",
                body=(f"Ticket {key} is blocked: {blocked_reason}." if blocked
                      else f"Ticket {key} is no longer blocked."),
                occurred_at=at, ref=key, url=f"{base_url}/tickets/{key}",
                tags=list(detail.get("labels") or []),
                flagged=blocked,
                meta={
                    "state": state,
                    "blocked": blocked,
                    "blocked_reason": blocked_reason,
                },
            ))

        if previous.get("implementer") != current.get("implementer"):
            actor, at = self._find_activity(activity, "implementer",
                                           current.get("implementer") or "", updated_at)
            signals.append(Signal(
                tenant=tenant, agent_id=agent_id, source="qiko_track",
                kind="ticket_assigned",
                external_id=f"{project}:{key}:assigned:{current.get('implementer') or ''}:{at.isoformat()}",
                container=project, actor=actor or "",
                title=f"{key} assigned to {current.get('implementer') or 'nobody'}",
                body=f"Ticket {key} implementer set to {current.get('implementer') or 'nobody'}.",
                occurred_at=at, ref=key, url=f"{base_url}/tickets/{key}",
                tags=list(detail.get("labels") or []),
                flagged=current.get("blocked") or False,
                meta={
                    "state": state,
                    "role": "implementer",
                    "implementer": current.get("implementer") or "",
                    "previous_implementer": previous.get("implementer") or "",
                },
            ))

        previous_comments = previous.get("comments") or 0
        if len(comments) > previous_comments:
            for comment in comments:
                created = self._parse_time(comment.get("createdAt"))
                if created and created <= since:
                    continue
                signals.append(self._comment_signal(
                    tenant, agent_id, base_url, project, key, detail,
                    comment, current.get("blocked") or False, state))

        return signals

    @staticmethod
    def _find_activity(activity: list[dict], field: str, to_value: str,
                       fallback_at: datetime) -> tuple[str, datetime]:
        """Find the latest activity event that changed `field` to `to_value`."""
        latest_at: datetime | None = None
        actor = ""
        for event in activity:
            if event.get("field") == field and str(event.get("to") or "").lower() == str(to_value).lower():
                at = PollAndDiff._parse_time(event.get("at"))
                if at and (latest_at is None or at > latest_at):
                    latest_at = at
                    actor = event.get("actor") or ""
        return actor, latest_at or fallback_at

    def _comment_signal(self, tenant: str, agent_id: str, base_url: str, project: str,
                        key: str, detail: dict, comment: dict, blocked: bool,
                        state: dict) -> Signal:
        author = comment.get("author") or ""
        body = comment.get("body") or ""
        created_at = self._parse_time(comment.get("createdAt")) or datetime.now(timezone.utc)
        body_hash = hashlib.sha256(body.encode()).hexdigest()[:12]
        return Signal(
            tenant=tenant, agent_id=agent_id, source="qiko_track",
            kind="comment",
            external_id=f"{project}:{key}:comment:{created_at.isoformat()}:{author}:{body_hash}",
            container=project, actor=author,
            title=f"Comment on {key}",
            body=body,
            occurred_at=created_at, ref=key, url=f"{base_url}/tickets/{key}",
            tags=list(detail.get("labels") or []),
            flagged=blocked,
            meta={"state": state},
        )
