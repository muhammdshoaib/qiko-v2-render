import hashlib
import hmac

from app.modules.billing.webhook import (
    StripeWebhookHandler,
    verify_stripe_signature,
)

SECRET = "whsec_test"


def _sig(payload: bytes, t: str = "1700000000") -> str:
    mac = hmac.new(SECRET.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def test_stripe_signature_verify():
    payload = b'{"id":"evt_1"}'
    assert verify_stripe_signature(SECRET, payload, _sig(payload)) is True
    assert verify_stripe_signature(SECRET, b'{"id":"tampered"}', _sig(payload)) is False
    assert verify_stripe_signature(SECRET, payload, "garbage") is False


def _invoice_event(eid: str, inv_id: str, amount: int, status: str = "paid") -> dict:
    return {"id": eid, "type": "invoice.paid",
            "data": {"object": {"id": inv_id, "customer": "cus_1", "amount_paid": amount, "status": status}}}


def test_invoice_sync_is_idempotent():
    h = StripeWebhookHandler()
    assert h.handle(_invoice_event("evt_1", "in_1", 5000)) == "invoice_synced"
    # same event id re-delivered -> ignored, no double count
    assert h.handle(_invoice_event("evt_1", "in_1", 5000)) == "duplicate"
    # new event, same invoice id, updated status -> upsert (still one invoice)
    assert h.handle(_invoice_event("evt_2", "in_1", 5000, "void")) == "invoice_synced"
    assert h.invoices.count() == 1
    assert h.invoices.get("in_1").status == "void"


def test_checkout_completed_and_ignored():
    h = StripeWebhookHandler()
    assert h.handle({"id": "e", "type": "checkout.session.completed", "data": {"object": {}}}) == "checkout_completed"
    assert h.handle({"id": "e2", "type": "customer.updated", "data": {"object": {}}}) == "ignored"
