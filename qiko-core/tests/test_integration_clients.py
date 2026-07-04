"""Unit tests for integration clients: assert request construction (URL/method/auth/body) and
response parsing using httpx.MockTransport — no network, no credentials."""
import json

import httpx

from app.integrations.clients import (
    CalendlyClient,
    ClickUpClient,
    GA4Client,
    SignalEngineClient,
    SlackClient,
    StripeClient,
    WhatsAppClient,
)


def _client(base_url: str, handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=base_url,
                        headers={"Authorization": "Bearer test"})


def test_stripe_checkout_builds_subscription_session():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"url": "https://checkout.stripe.com/x"})

    c = StripeClient(client=_client("https://api.stripe.com/v1", handler))
    url = c.create_checkout_session(customer_id="cus_1", price_id="price_1", promo="PROMO")
    assert url == "https://checkout.stripe.com/x"
    assert seen["url"].endswith("/checkout/sessions")
    assert "mode=subscription" in seen["body"] and "cus_1" in seen["body"] and "PROMO" in seen["body"]


def test_whatsapp_send_text_meta_shape():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["json"] = json.loads(req.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    c = WhatsAppClient(phone_number_id="PID", client=_client("https://graph.facebook.com/v21.0", handler))
    out = c.send_text("15550001111", "hello")
    assert out["messages"][0]["id"] == "wamid.1"
    assert seen["url"].endswith("/PID/messages")
    assert seen["json"]["messaging_product"] == "whatsapp" and seen["json"]["text"]["body"] == "hello"


def test_slack_post_message_and_error():
    def ok(req):
        return httpx.Response(200, json={"ok": True, "ts": "1.2"})

    assert SlackClient(client=_client("https://slack.com/api", ok)).send_message("#c", "hi")["ok"] is True

    def bad(req):
        return httpx.Response(200, json={"ok": False, "error": "not_in_channel"})

    import pytest
    with pytest.raises(RuntimeError):
        SlackClient(client=_client("https://slack.com/api", bad)).send_message("#c", "hi")


def test_clickup_create_task():
    def handler(req):
        assert str(req.url).endswith("/list/L1/task")
        return httpx.Response(200, json={"id": "task1"})

    out = ClickUpClient(client=_client("https://api.clickup.com/api/v2", handler)).create_task("L1", "N", "D")
    assert out["id"] == "task1"


def test_calendly_available_slots():
    def handler(req):
        return httpx.Response(200, json={"collection": [{"start_time": "2026-07-10T10:00:00Z"}]})

    slots = CalendlyClient(client=_client("https://api.calendly.com", handler)).available_slots("et1")
    assert slots == ["2026-07-10T10:00:00Z"]


def test_signal_engine_flow():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/projects":
            return httpx.Response(200, json={"project_id": "p1"})
        if req.url.path == "/scans":
            return httpx.Response(200, json={"scan_id": "s1"})
        return httpx.Response(200, json={"scan_id": "s1", "score": 72})

    c = SignalEngineClient(client=_client("https://signal.test", handler))
    assert c.create_project("acme", "IDG", "idg.example")["project_id"] == "p1"
    assert c.run_scan("p1")["scan_id"] == "s1"
    assert c.get_score("s1")["score"] == 72


def test_ga4_run_report_parses_rows():
    def handler(req):
        return httpx.Response(200, json={
            "dimensionHeaders": [{"name": "pagePath"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [{"dimensionValues": [{"value": "/"}], "metricValues": [{"value": "100"}]}],
        })

    rows = GA4Client(property_id="123", client=_client("https://analyticsdata.googleapis.com/v1beta", handler)).run_report(
        "2026-07-01", "2026-07-07", ["sessions"], ["pagePath"])
    assert rows == [{"pagePath": "/", "sessions": "100"}]
