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
import ipaddress
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
# Values that are recognisably credentials regardless of what the key is called. NOT anchored: an
# earlier version used ^ and therefore missed "Bearer sk_live_...", which is the shape a secret
# actually arrives in.
_SECRET_VALUE_PATTERN = re.compile(
    r"(sk_live_|sk_test_|whsec_|xoxb-|xoxp-|ghp_|AKIA[0-9A-Z]{16}|-----BEGIN|ey[A-Za-z0-9_-]{10,}\.)",
)
# Containers we know how to walk. Anything else is stringified and screened rather than trusted:
# a dataclass or a pydantic model reaching the JSON serialiser would dump every attribute it has.
_WALKABLE = (list, tuple, set, frozenset)
REDACTED = "[redacted]"

# An audit row must never become an exfiltration channel or a log-bloat vector.
MAX_METADATA_BYTES = 8_192
MAX_REASON_CHARS = 1_000
# The width of the identity columns in audit_events. Capped HERE rather than only at each request
# model, because this is the one place every present and future call site passes through.
#
# Uncapped, these were an audit-suppression vector: a 400-character email on a failed login made the
# INSERT raise StringDataRightTruncation, record() swallowed it by design, and the caller still got a
# clean 401. The one row an attacker cares about was the one they could switch off with whitespace.
MAX_IDENTITY_CHARS = 320
MAX_TENANT_CHARS = 64


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
    key = get_settings().encryption_key
    if not key:
        # Refuses rather than falling back to a constant. A public HMAC key turns the fingerprint into
        # an offline verification oracle for any low-entropy secret, which is worse than no
        # fingerprint. encryption_key is empty only in dev, where assert_secrets_set does not run.
        return None
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()[:12]


MAX_VALUE_CHARS = 2_000


def _fit(value: str | None, limit: int = MAX_IDENTITY_CHARS) -> str | None:
    """Truncate to the column width. Never let an oversized value become a lost row."""
    if value is None:
        return None
    return str(value)[:limit] or None


def _scrub(value: Any, depth: int = 0) -> Any:
    """Reduce a value to something safe to store.

    Fails closed at every branch. The allowlist is the real defence; this exists for the case where
    someone adds a field to an allowlist without thinking about what can be inside it, so it has to
    assume the worst about shapes it does not recognise.
    """
    if depth > 4:
        return REDACTED
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            text_key = str(key)
            # A secret can be the KEY as easily as the value, and a key is written verbatim.
            if _SECRET_VALUE_PATTERN.search(text_key):
                return REDACTED
            out[text_key] = REDACTED if _SECRET_KEY_PATTERN.search(text_key) else _scrub(item, depth + 1)
        return out
    if isinstance(value, _WALKABLE):
        # Tuples, sets and frozensets used to fall through untouched, and a set is not even JSON
        # serialisable, so the row would have failed at flush instead of being redacted.
        return [_scrub(item, depth + 1) for item in list(value)[:50]]
    if value is None or isinstance(value, bool | int | float):
        # Screened as text too: a numeric one-time code is still a credential.
        return REDACTED if _SECRET_VALUE_PATTERN.search(str(value)) else value
    if isinstance(value, str):
        if _SECRET_VALUE_PATTERN.search(value):
            return REDACTED
        return value[:MAX_VALUE_CHARS]
    # Anything else: an object, bytes, a dataclass. Stringified and screened rather than handed to a
    # JSON serialiser that would repr every attribute.
    text = str(value)
    return REDACTED if _SECRET_VALUE_PATTERN.search(text) else text[:MAX_VALUE_CHARS]


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

    # Strictly the action's allowlist. An earlier version also let through top-level "from"/"to",
    # which diff() never produces and which therefore only served as a hole large enough to carry
    # anything at all.
    changes = _scrub({k: v for k, v in (event.changes or {}).items() if k in spec.diff_fields})
    if len(json.dumps(changes, default=str)) > MAX_METADATA_BYTES:
        # Several allowlisted fields are tenant free text, so the diff needs the same ceiling the
        # metadata already had.
        changes = {"truncated": True, "fields": sorted(changes)}
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
        "message": _render(spec.template, event, changes),
        "occurred_at": event.occurred_at,
        "actor_type": event.actor_type,
        "actor_id": _fit(event.actor_id),
        "actor_label": _fit(event.actor_label),
        "on_behalf_of": _fit(event.on_behalf_of, MAX_TENANT_CHARS),
        "target_type": spec.target_type,
        "target_id": _fit(event.target_id),
        "target_label": _fit(event.target_label),
        # The tenant the event is ABOUT, which is not always the actor's own.
        "tenant_id": _fit(event.tenant_id or get_tenant(), MAX_TENANT_CHARS),
        "request_id": get_request_id(),
        "source_ip": _client_ip(headers, client),
        "user_agent": (headers.get("user-agent") or "")[:256] or None,
        "route": route,
        "service": os.environ.get("QIKO_SERVICE", "api"),
        "environment": settings.environment.value,
        "changes": changes,
        "event_metadata": metadata,
        "reason": (event.reason or "")[:MAX_REASON_CHARS] or None,
    }


def _client_ip(headers, client) -> str | None:
    """The caller's address, from a header the client cannot forge.

    NOT the leftmost X-Forwarded-For. Cloudflare APPENDS to that header rather than replacing it, and
    Caddy forwards it upstream untrimmed, so `X-Forwarded-For: 8.8.8.8` from any client lands in the
    leftmost position. Recording it would be attribution poisoning in the one store that exists for
    attribution. CF-Connecting-IP is overwritten by Cloudflare on every request, and scope["client"]
    has already been rewritten by uvicorn's proxy-headers handling within FORWARDED_ALLOW_IPS.

    Validated before storing, so a malformed header cannot become a value that looks like an address.
    """
    candidate = (headers.get("cf-connecting-ip") or "").strip() if headers else ""
    if not candidate and client is not None:
        candidate = getattr(client, "host", "") or ""
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _render(template: str, event: AuditEvent, changes: dict) -> str:
    """Render the sentence from the SCRUBBED diff.

    Reading the raw changes here would have let a value that _scrub redacted reappear verbatim in a
    column every reader sees. The diff shape also matters: diff() produces {"provider": {"from":
    ..., "to": ...}}, so taking the field directly would have rendered a dict into the sentence.
    """
    if not template:
        return event.action
    provider = changes.get("provider", "")
    if isinstance(provider, dict):
        provider = provider.get("to") or provider.get("from") or ""
    try:
        return template.format(
            actor=event.actor_label or event.actor_id or "system",
            target=event.target_label or event.target_id or "",
            provider=provider,
        )[:512]
    except Exception:  # noqa: BLE001 - a template typo must never take down a write, least of all one
        # inside a caller's transaction. The registry test renders every template so this stays unhit.
        logger.error("audit template failed to render", extra={
            "source": "audit", "action": event.action})
        return event.action


# Fields safe to echo into application logs. Deliberately excludes every label, the reason, the IP and
# the user agent: those are the row's PII payload, and application logs sit outside this store's
# retention window and outside its erasure path, so pseudonymising a row would leave the same data
# behind in the log stream.
_MIRROR_FIELDS = ("event_id", "action", "category", "outcome", "actor_type", "target_type",
                  "tenant_id", "request_id", "environment", "service")


def _mirror(row: dict) -> None:
    """A correlation line on stdout alongside the row.

    Logged at WARNING, not INFO, because live runs LOG_LEVEL=WARNING: at INFO this was silently
    dropped in production, so the backstop it claimed to provide did not exist where it mattered.
    Identifiers only, so it is a pointer into the audit store rather than a second copy of it.
    """
    logger.warning("audit", extra={"source": "audit", "audit_event": {
        field: row.get(field) for field in _MIRROR_FIELDS}})


async def record_in(session, store, event: AuditEvent, *, request=None) -> None:
    """Write inside the caller's transaction. For CRITICAL actions only."""
    row = build_row(event, request=request)
    store.add_in(session, row)
    _mirror(row)


async def record(store, event: AuditEvent, *, request=None) -> None:
    """Write after the fact, never raising. For everything below CRITICAL.

    A CRITICAL action arriving here is a wiring mistake, not a runtime condition: the whole point of
    the durability split is that money, access, credentials and deletions cannot be written on a path
    that is allowed to lose the row. It is logged rather than raised, because refusing at this point
    would fail a request whose mutation has already committed, which is the exact outcome the
    non-fatal rule exists to avoid. The route-coverage test is what stops it happening.
    """
    if store is None:
        return
    if is_critical(event.action):
        logger.error("critical audit event written on the non-transactional path", extra={
            "source": "audit", "action": event.action, "target": event.target_id})
    row = build_row(event, request=request)
    _mirror(row)
    try:
        await store.add(row)
    except Exception as error:  # noqa: BLE001 - see the module docstring
        # Loud, because a persistently failing audit path must not be discoverable only by its absence.
        logger.error("audit write failed", extra={
            "source": "audit", "action": event.action, "target": event.target_id,
            "actor": event.actor_label, "error": str(error)})


def record_sync(store, event: AuditEvent, *, request=None) -> None:
    """Write from a synchronous handler, never raising.

    The billing endpoints are plain `def`, so they run in a threadpool and cannot await. Rather than
    make them async (which would put a blocking Stripe call on the event loop, a much worse trade),
    the row is written through the store's synchronous path. asyncio.to_thread propagates context
    variables, so the request id and tenant are still correct here.
    """
    if store is None:
        return
    if is_critical(event.action):
        # Same guard as record(). Without it, payment_link_marked_paid was declared CRITICAL and
        # written on the path that is allowed to lose the row, which is the exact inversion the
        # durability split exists to prevent.
        logger.error("critical audit event written on the non-transactional path", extra={
            "source": "audit", "action": event.action, "target": event.target_id})
    row = build_row(event, request=request)
    _mirror(row)
    try:
        store.add_sync(row)
    except Exception as error:  # noqa: BLE001 - see the module docstring
        logger.error("audit write failed", extra={
            "source": "audit", "action": event.action, "target": event.target_id,
            "actor": event.actor_label, "error": str(error)})


def is_critical(action: str) -> bool:
    return spec_for(action).durability == CRITICAL


@dataclass
class InMemoryAuditStore:
    """Dev and test store. Mirrors the SQL store's filtering so tests exercise the real semantics."""

    rows: list[dict] = field(default_factory=list)

    _next_id: int = 1

    def add_in(self, _session, row: dict) -> None:
        self._assign(row)

    async def add(self, row: dict) -> None:
        self._assign(row)

    def add_sync(self, row: dict) -> None:
        self._assign(row)

    def _assign(self, row: dict) -> None:
        # The SQL store gets its id from the database. Without one here the router's cursor handling
        # raised on any page past the first, so dev and tests diverged from production exactly where
        # the paging bug lived.
        self.rows.append({**row, "_row_id": self._next_id})
        self._next_id += 1

    async def apply_retention(self, now=None) -> dict:
        from app.modules.audit.retention import cutoffs

        event_cutoff, network_cutoff = cutoffs(now)
        before = len(self.rows)
        self.rows = [row for row in self.rows if row["occurred_at"] >= event_cutoff]
        cleared = 0
        for row in self.rows:
            if row["occurred_at"] < network_cutoff and (row.get("source_ip") or row.get("user_agent")):
                row["source_ip"] = None
                row["user_agent"] = None
                cleared += 1
        return {"events_deleted": before - len(self.rows), "addresses_cleared": cleared,
                "cutoff_events": event_cutoff.isoformat(),
                "cutoff_network": network_cutoff.isoformat()}

    async def pseudonymise_subject(self, identifier: str, pseudonym: str, *,
                                   audit_row=None) -> int:
        needle = identifier.strip().lower()
        matching = [row for row in self.rows
                    if needle in {str(row.get(field) or "").lower() for field in
                                  ("target_id", "target_label", "actor_id", "actor_label")}]
        if audit_row is not None:
            self._assign(audit_row(len(matching)))
        touched = 0
        for row in list(self.rows):
            if needle in {str(row.get(field) or "").lower() for field in
                          ("target_id", "target_label", "actor_id", "actor_label")}:
                # message is rendered from the labels, so it carries the address too. Leaving it
                # would put the erased value back in the one field a human reads.
                row.update(target_id=pseudonym, target_label=None, actor_id=pseudonym,
                           actor_label=None, source_ip=None, user_agent=None,
                           message=row["action"], subject_pseudonym=pseudonym,
                           pseudonymised_at=datetime.now(timezone.utc))
                touched += 1
        return touched

    async def list(self, *, actions_to_hide=None, action=None, category=None, outcome=None,
                   tenant_id=None, actor_id=None, target_id=None, request_id=None, search=None,
                   since=None, until=None, cursor=None, limit=100) -> list[dict]:
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
        # Same order and same cursor semantics as SQL, including the tiebreak, so a paging bug cannot
        # hide in the difference between the two stores.
        rows = sorted(rows, key=lambda row: (row["occurred_at"], row["_row_id"]), reverse=True)
        if cursor is not None:
            cursor_time, cursor_id = cursor
            rows = [row for row in rows
                    if (row["occurred_at"], row["_row_id"]) < (cursor_time, cursor_id)]
        out = []
        for row in rows[:limit]:
            item = {k: v for k, v in row.items() if k not in {"_row_id", "event_metadata"}}
            item["metadata"] = row.get("event_metadata", {})
            item["occurred_at"] = row["occurred_at"].isoformat()
            item["_cursor"] = f"{row['occurred_at'].isoformat()}|{row['_row_id']}"
            out.append(item)
        return out
