"""Inbound channel webhooks: signature verification + idempotency.

Every inbound webhook (WhatsApp, Slack, Google) must be signature-verified before we act on it,
and duplicate deliveries (same event id) are ignored. Heavy handling (and voice transcription)
is offloaded to the worker tier, never done inline.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def verify_hmac_signature(secret: str, body: bytes, signature: str) -> bool:
    """Generic HMAC-SHA256 body signature (WhatsApp/Google style: 'sha256=<hex>')."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature.split("=", 1)[1] if "=" in signature else signature
    return hmac.compare_digest(expected, provided)


def verify_slack_signature(signing_secret: str, timestamp: str, body: bytes, signature: str,
                           *, tolerance_seconds: int = 300) -> bool:
    """Slack v0 request signing: HMAC over 'v0:{ts}:{body}', with a replay window.

    The signature alone is replayable forever: a captured request stays valid because the
    HMAC covers only the timestamp and the body, and the event-id dedupe is per-process, so
    it is reset by every restart. Rejecting a stale timestamp is the control Slack documents
    for exactly this, and it fails CLOSED on a timestamp that is missing or not an integer.
    """
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        age = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        return False
    if age > tolerance_seconds:
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

    BOUNDED, because it is now on a path (the Slack Events API) that receives one id per message
    rather than one per payment: an unbounded set on a busy workspace is a slow memory leak in a
    512M container. Oldest ids are evicted first, so the window is recent-N rather than forever --
    which is what a redelivery window actually needs.
    """

    max_entries: int = 50_000
    _seen: OrderedDict[str, None] = field(default_factory=OrderedDict)

    def is_duplicate(self, event_id: str) -> bool:
        if event_id in self._seen:
            return True
        self._seen[event_id] = None
        while len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)
        return False


@dataclass
class RedisIdempotencyGuard:
    """Redis-backed replacement for IdempotencyGuard (JM2-1025), safe across replicas.

    `SET key value NX EX ttl` is atomic in Redis: two replicas racing on the same delivery id
    can never both see "not a duplicate" the way two processes each checking their own in-memory
    OrderedDict independently could. Namespaced by event source (e.g. "interakt") so a message
    id from one channel can never collide with an unrelated one from another.

    Fails OPEN (treated as "not a duplicate") on any Redis error, same reasoning as
    RateLimitMiddleware's own try/except around `limiter.allow()`: dedupe here is a protection
    against double-processing a redelivered webhook, not a correctness guarantee the channel's
    own delivery semantics already provide - an occasional double-send during a Redis outage is
    a far smaller problem than silently dropping every inbound message until Redis recovers.
    """

    redis: Any
    namespace: str = "qiko:idempotency"
    ttl_seconds: int = 60 * 60 * 24  # generous redelivery window; a duplicate id older than a day is not coming back

    async def is_duplicate(self, event_id: str) -> bool:
        key = f"{self.namespace}:{event_id}"
        try:
            was_set = await self.redis.set(key, "1", nx=True, ex=self.ttl_seconds)
        except Exception:
            logger.warning("idempotency_backend_unavailable_failing_open",
                           extra={"source": "channels.idempotency", "namespace": self.namespace})
            return False
        return not was_set
