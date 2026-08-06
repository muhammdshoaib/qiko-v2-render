"""Building and writing audit events.

Two write paths, and choosing between them is the most consequential decision in this module.

`record_in(session, event)` writes the row inside the caller's transaction. A mutation then cannot
commit without its audit row, and a rolled-back mutation cannot leave one behind. Used for everything
the registry marks CRITICAL: money, access, credentials, deletions.

`record(store, event)` writes afterwards and never raises. Used for everything else. The reasoning is
the same one the codebase already applies to cost accounting: the mutation is already committed and its
result already returned to the caller, so failing the response would make an operator repeat a change
that succeeded. That is the right trade for a worker status change and the wrong one for a payment
link, which is why the two paths exist rather than one.

Context is read here rather than threaded through call sites. The request id, tenant, IP, user agent
and route are all already available in context variables or on the request, and passing them through
forty call sites would guarantee that some of them are wrong.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.observability import get_request_id
from app.core.tenancy import get_tenant
from app.modules.audit.registry import CRITICAL, spec_for

logger = logging.getLogger(__name__)

# Actor kinds. The rule that matters: for support access the HUMAN who initiated is always the actor,
# and the impersonated identity goes in on_behalf_of. Recording the impersonated user as the actor is
# the mistake that makes an audit trail useless in exactly the situation it exists for.
USER = "user"
PLATFORM_ADMIN = "platform_admin"
SYSTEM = "system"
JOB = "job"
WEBHOOK = "webhook"
ANONYMOUS = "anonymous"

SUCCESS = "success"
FAILURE = "failure"
DENIED = "denied"

# Belt and braces over the per-action allowlist. The allowlist is the real defence; this catches the
# case where someone adds a field to an allowlist without thinking about what is in it.
_SECRET_KEY_PATTERN = re.compile(
    r"secret|password|passwd|token|api[_-]?key|credential|totp|cookie|authorization|"
    r"signature|private[_-]?key|bearer|encrypted",
    re.IGNORECASE,
)
# Values that are recognisably credentials regardless of what the key is called.
_SECRET_VALUE_PATTERN = re.compile(
    r"^(sk_live_|sk_test_|whsec_|xoxb-|xoxp-|ghp_|AKIA|-----BEGIN|ey[A-Za-z0-9_-]{10,}\.)",
)
REDACTED = "[redacted]"

# An audit row must never become an exfiltration channel or a log-bloat vector.
MAX_METADATA_BYTES = 8_192
MAX_REASON_CHARS = 1_000


@dataclass(frozen=True)
class AuditEvent:
    action: str
    target_id: str | None = None
    target_label: str | None = None
    tenant_id: str | None = None
    actor_type: str = SYSTEM
    actor_id: str | None = None
    actor_label: str | None = None
    outcome: str = SUCCESS
    changes: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    on_behalf_of: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditStore(Protocol):
    async def add(self, row: dict) -> None: ...
    async def list(self, **filters) -> list[dict]: ...


def fingerprint_of(value: str | None) -> str | None:
    """A keyed, truncated fingerprint of a secret, so a rotation is distinguishable from a re-save.

    Keyed rather than a plain digest, so the fingerprint is not an offline verification oracle for a
    low-entropy value. Truncated so it is not a full digest to attack. This is the whole answer to
    "record that a secret changed without recording the secret": a bare changed=true cannot tell an
    incident responder whether the value was actually rotated or merely saved again.
    """
    if not value:
        return None
    key = (get_settings().encryption_key or "audit").encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:12]


def _scrub(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return REDACTED
    if isinstance(value, dict):
        return {k: (REDACTED if _SECRET_KEY_PATTERN.search(str(k)) else _scrub(v, depth + 1))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(item, depth + 1) for item in value[:50]]
    if isinstance(value, str) and _SECRET_VALUE_PATTERN.search(value):
        return REDACTED
    return value


def diff(spec_action: str, before: dict | None, after: dict | None) -> dict:
    """A field-level diff restricted to the action's allowlist, with only the changed fields.

    Not a snapshot of either side. A snapshot duplicates personal data into a second store, and in this
    codebase it would also copy encrypted credentials out of a worker config. Only changed fields
    appear, which is both minimisation and readability: the reader does not have to diff by eye.
    """
    allowed = set(spec_for(spec_action).diff_fields)
    before = before or {}
    after = after or {}
    changed: dict[str, Any] = {}
    for key in allowed:
        old, new = before.get(key), after.get(key)
        if key in before or key in after:
            if old != new:
                changed[key] = {"from": _scrub(old), "to": _scrub(new)}
    return changed


def build_row(event: AuditEvent, *, request=None) -> dict:
    """Turn an event into the row, filling context the caller should not have to know about."""
    spec = spec_for(event.action)
    settings = get_settings()

    changes = _scrub({k: v for k, v in (event.changes or {}).items()
                      if k in spec.diff_fields or k in {"from", "to"}})
    metadata = _scrub(event.metadata or {})
    encoded = json.dumps(metadata, default=str)
    if len(encoded) > MAX_METADATA_BYTES:
        # Truncated explicitly rather than silently, so a reader knows something was dropped.
        metadata = {"truncated": True, "original_bytes": len(encoded)}

    headers = getattr(request, "headers", {}) if request is not None else {}
    client = getattr(request, "client", None) if request is not None else None
    route = None
    if request is not None:
        route = f"{request.method} {getattr(request.scope.get('route'), 'path', request.url.path)}"

    return {
        "event_id": str(uuid.uuid4()),
        "action": event.action,
        "category": spec.category,
        "outcome": event.outcome,
        "message": _render(spec.template, event),
        "occurred_at": event.occurred_at,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "actor_label": event.actor_label,
        "on_behalf_of": event.on_behalf_of,
        "target_type": spec.target_type,
        "target_id": event.target_id,
        "target_label": event.target_label,
        # The tenant the event is ABOUT, which is not always the actor's own.
        "tenant_id": event.tenant_id or get_tenant(),
        "request_id": get_request_id(),
        # Trusted only as far as the proxy allowlist already trusts it; see FORWARDED_ALLOW_IPS.
        "source_ip": (headers.get("x-forwarded-for", "").split(",")[0].strip()
                      or (client.host if client else None)) or None,
        "user_agent": (headers.get("user-agent") or "")[:256] or None,
        "route": route,
        "service": os.environ.get("QIKO_SERVICE", "api"),
        "environment": settings.environment.value,
        "changes": changes,
        "event_metadata": metadata,
        "reason": (event.reason or "")[:MAX_REASON_CHARS] or None,
    }


def _render(template: str, event: AuditEvent) -> str:
    if not template:
        return event.action
    try:
        return template.format(
            actor=event.actor_label or event.actor_id or "system",
            target=event.target_label or event.target_id or "",
            provider=(event.changes or {}).get("provider", ""),
        )[:512]
    except (KeyError, IndexError):  # pragma: no cover - a template typo, caught by the registry test
        return event.action


def _mirror(row: dict) -> None:
    """A structured line on stdout as well as the row.

    Costs nothing and buys two things: a backstop if the insert fails, and log streaming becomes a
    shipping config change rather than a project if a customer ever asks for it.
    """
    logger.info("audit", extra={"source": "audit", "audit_event": {
        k: v for k, v in row.items() if k not in {"changes", "event_metadata"}}})


async def record_in(session, store, event: AuditEvent, *, request=None) -> None:
    """Write inside the caller's transaction. For CRITICAL actions only."""
    row = build_row(event, request=request)
    store.add_in(session, row)
    _mirror(row)


async def record(store, event: AuditEvent, *, request=None) -> None:
    """Write after the fact, never raising. For everything below CRITICAL."""
    if store is None:
        return
    row = build_row(event, request=request)
    _mirror(row)
    try:
        await store.add(row)
    except Exception as error:  # noqa: BLE001 - see the module docstring
        # Loud, because a persistently failing audit path must not be discoverable only by its absence.
        logger.error("audit write failed", extra={
            "source": "audit", "action": event.action, "target": event.target_id,
            "actor": event.actor_label, "error": str(error)})


def is_critical(action: str) -> bool:
    return spec_for(action).durability == CRITICAL


@dataclass
class InMemoryAuditStore:
    """Dev and test store. Mirrors the SQL store's filtering so tests exercise the real semantics."""

    rows: list[dict] = field(default_factory=list)

    def add_in(self, _session, row: dict) -> None:
        self.rows.append(row)

    async def add(self, row: dict) -> None:
        self.rows.append(row)

    async def list(self, *, actions_to_hide=None, action=None, category=None, outcome=None,
                   tenant_id=None, actor_id=None, target_id=None, request_id=None, search=None,
                   since=None, until=None, cursor_id=None, limit=100) -> list[dict]:
        hidden = set(actions_to_hide or ())
        rows = [row for row in self.rows if row["action"] not in hidden]
        for key, value in (("action", action), ("category", category), ("outcome", outcome),
                           ("tenant_id", tenant_id), ("actor_id", actor_id),
                           ("target_id", target_id), ("request_id", request_id)):
            if value is not None:
                rows = [row for row in rows if row.get(key) == value]
        if since is not None:
            rows = [row for row in rows if row["occurred_at"] >= since]
        if until is not None:
            rows = [row for row in rows if row["occurred_at"] <= until]
        if search:
            needle = search.lower()
            rows = [row for row in rows if needle in " ".join(
                str(row.get(field_name) or "") for field_name in
                ("message", "actor_label", "target_label")).lower()]
        rows = sorted(rows, key=lambda row: row["occurred_at"], reverse=True)
        return [{**row, "metadata": row.get("event_metadata", {}),
                 "occurred_at": row["occurred_at"].isoformat()} for row in rows[:limit]]
