"""Inbound channel webhooks: signature verification + idempotency.

Every inbound webhook (WhatsApp, Slack, Google) must be signature-verified before we act on it,
and duplicate deliveries (same event id) are ignored. Heavy handling (and voice transcription)
is offloaded to the worker tier, never done inline.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field


def verify_hmac_signature(secret: str, body: bytes, signature: str) -> bool:
    """Generic HMAC-SHA256 body signature (WhatsApp/Google style: 'sha256=<hex>')."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature.split("=", 1)[1] if "=" in signature else signature
    return hmac.compare_digest(expected, provided)


def verify_slack_signature(signing_secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Slack v0 request signing: HMAC over 'v0:{ts}:{body}'."""
    if not signing_secret or not timestamp or not signature:
        return False
    basestring = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@dataclass
class IdempotencyGuard:
    """Rejects duplicate event ids.

    In-memory (per-process) only today -- correct for the current single-replica deployment, but
    NOT safe once the API runs behind more than one replica: a duplicate delivery routed to a
    different pod won't be caught. Before scaling out, back this with a Redis SET + TTL
    (app.core.redis.build_redis is the client factory already in place for that) so the dedupe
    state is shared across replicas instead of local to each process.
    """

    _seen: set[str] = field(default_factory=set)

    def is_duplicate(self, event_id: str) -> bool:
        if event_id in self._seen:
            return True
        self._seen.add(event_id)
        return False
