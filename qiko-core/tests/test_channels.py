import hashlib
import hmac
import time

from app.modules.channels.webhooks import (
    IdempotencyGuard,
    RedisIdempotencyGuard,
    verify_hmac_signature,
    verify_slack_signature,
)

SECRET = "shhh"


def _hmac(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_hmac_signature_accepts_valid_rejects_tampered():
    body = b'{"event":"message"}'
    assert verify_hmac_signature(SECRET, body, _hmac(body)) is True
    assert verify_hmac_signature(SECRET, b'{"event":"tampered"}', _hmac(body)) is False
    assert verify_hmac_signature(SECRET, body, "") is False
    assert verify_hmac_signature("", body, _hmac(body)) is False


def _slack_sig(ts: str, body: bytes) -> str:
    base = f"v0:{ts}:".encode() + body
    return "v0=" + hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()


def test_slack_signature():
    body = b"payload=xyz"
    # A CURRENT timestamp: the signature is only accepted inside the replay window, so a fixed
    # timestamp would have made this test pass in 2023 and fail forever afterwards.
    ts = str(int(time.time()))
    sig = _slack_sig(ts, body)
    assert verify_slack_signature(SECRET, ts, body, sig) is True
    assert verify_slack_signature(SECRET, ts, b"tampered", sig) is False
    assert verify_slack_signature(SECRET, "", body, sig) is False


def test_slack_signature_rejects_a_replayed_request():
    """A valid signature stays valid forever, so freshness is the only thing stopping a replay."""
    body = b"payload=xyz"
    stale = str(int(time.time()) - 301)
    assert verify_slack_signature(SECRET, stale, body, _slack_sig(stale, body)) is False

    future = str(int(time.time()) + 301)
    assert verify_slack_signature(SECRET, future, body, _slack_sig(future, body)) is False


def test_slack_signature_rejects_an_unparseable_timestamp():
    body = b"payload=xyz"
    assert verify_slack_signature(SECRET, "not-a-number", body, _slack_sig("not-a-number", body)) is False


def test_idempotency_guard_ignores_duplicates():
    g = IdempotencyGuard()
    assert g.is_duplicate("evt-1") is False  # first time
    assert g.is_duplicate("evt-1") is True   # duplicate
    assert g.is_duplicate("evt-2") is False


def test_idempotency_guard_is_bounded_and_evicts_oldest_first():
    """It is now on a per-message path, so an unbounded set would be a slow memory leak."""
    g = IdempotencyGuard(max_entries=3)
    for event_id in ("a", "b", "c"):
        assert g.is_duplicate(event_id) is False
    assert g.is_duplicate("d") is False          # evicts "a"
    assert len(g._seen) == 3
    assert g.is_duplicate("a") is False          # forgotten, so treated as new
    assert g.is_duplicate("d") is True           # still remembered


class _FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self.calls: list[tuple] = []

    async def set(self, key, value, *, nx=False, ex=None):
        self.calls.append((key, value, nx, ex))
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True


class _ExplodingRedis:
    async def set(self, *args, **kwargs):
        raise ConnectionError("redis unreachable")


async def test_redis_idempotency_guard_ignores_duplicates_atomically():
    redis = _FakeRedis()
    g = RedisIdempotencyGuard(redis=redis, namespace="interakt")
    assert await g.is_duplicate("evt-1") is False
    assert await g.is_duplicate("evt-1") is True
    assert await g.is_duplicate("evt-2") is False
    assert redis.calls[0] == ("interakt:evt-1", "1", True, g.ttl_seconds)


async def test_redis_idempotency_guard_namespaces_keys_so_channels_cannot_collide():
    redis = _FakeRedis()
    interakt = RedisIdempotencyGuard(redis=redis, namespace="interakt")
    slack = RedisIdempotencyGuard(redis=redis, namespace="slack")
    assert await interakt.is_duplicate("shared-id") is False
    assert await slack.is_duplicate("shared-id") is False  # different namespace, not a duplicate


async def test_redis_idempotency_guard_fails_open_on_backend_error():
    g = RedisIdempotencyGuard(redis=_ExplodingRedis())
    assert await g.is_duplicate("evt-1") is False
