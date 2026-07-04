import hashlib
import hmac

from app.modules.channels.webhooks import (
    IdempotencyGuard,
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


def test_slack_signature():
    body = b"payload=xyz"
    ts = "1700000000"
    base = f"v0:{ts}:".encode() + body
    sig = "v0=" + hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()
    assert verify_slack_signature(SECRET, ts, body, sig) is True
    assert verify_slack_signature(SECRET, ts, b"tampered", sig) is False
    assert verify_slack_signature(SECRET, "", body, sig) is False


def test_idempotency_guard_ignores_duplicates():
    g = IdempotencyGuard()
    assert g.is_duplicate("evt-1") is False  # first time
    assert g.is_duplicate("evt-1") is True   # duplicate
    assert g.is_duplicate("evt-2") is False
