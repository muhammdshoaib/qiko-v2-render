"""Webhook signature verification (SEC-2/SEC-3): signed webhooks pass, unsigned/invalid rejected."""
import hashlib
import hmac
import json
import time

_PAYLOAD = {"entry": [{"changes": [{"value": {"messages": [
    {"id": "wamid.1", "from": "155", "type": "text", "text": {"body": "hi"}}]}}]}]}


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_whatsapp_inbound_verifies_signature(client, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "whatsapp_app_secret", "wa-secret")
    # Inbound routing is off by default (audit H9: the adapter discarded messages while answering 200),
    # and this test is about the signature check, so enable it explicitly.
    monkeypatch.setattr(config.get_settings(), "channels_inbound_enabled", True)
    body = json.dumps(_PAYLOAD).encode()

    # valid signature -> processed
    ok = client.post("/api/v1/channels/whatsapp/webhook", content=body,
                     headers={"X-Hub-Signature-256": _sig("wa-secret", body), "Content-Type": "application/json"})
    assert ok.status_code == 200 and ok.json()["processed"] == ["wamid.1"]

    # missing/invalid signature -> 403
    bad = client.post("/api/v1/channels/whatsapp/webhook", content=body,
                      headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"})
    assert bad.status_code == 403


def test_stripe_webhook_verifies_signature(client, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "stripe_webhook_secret", "sk-whsec")
    body = json.dumps({"id": "evt1", "type": "invoice.paid",
                       "data": {"object": {"id": "in1", "customer": "c", "amount_paid": 100, "status": "paid"}}}).encode()
    t = str(int(time.time()))
    v1 = hmac.new(b"sk-whsec", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    ok = client.post("/api/v1/billing/webhook/stripe", content=body,
                     headers={"Stripe-Signature": f"t={t},v1={v1}", "Content-Type": "application/json"})
    assert ok.status_code == 200
    bad = client.post("/api/v1/billing/webhook/stripe", content=body,
                      headers={"Stripe-Signature": "t=1,v1=bad", "Content-Type": "application/json"})
    assert bad.status_code == 400
