"""Unit tests for integration clients: assert request construction (URL/method/auth/body) and
response parsing using httpx.MockTransport — no network, no credentials."""
import json

import httpx
import pytest

from app.integrations.clients import (
    CalendlyClient,
    ClickUpClient,
    GA4Client,
    SalesforceAuthError,
    SalesforceClient,
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


def test_stripe_checkout_omits_customer_when_not_real_and_links_via_reference():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"url": "https://checkout.stripe.com/x"})

    c = StripeClient(client=_client("https://api.stripe.com/v1", handler))
    # customer_id is the tenant string (not a real cus_...): must NOT be sent as `customer` (Stripe
    # 400s on an unknown customer). client_reference_id + metadata[plan] still link/activate correctly.
    url = c.create_checkout_session(customer_id="acme", price_id="price_pro",
                                    client_reference_id="acme", plan="pro")
    assert url == "https://checkout.stripe.com/x"
    body = seen["body"]
    assert "customer=" not in body  # tenant string omitted
    assert "client_reference_id=acme" in body
    assert "metadata%5Bplan%5D=pro" in body or "metadata[plan]=pro" in body

    # A real Stripe customer id IS forwarded.
    c.create_checkout_session(customer_id="cus_real123", price_id="price_pro", client_reference_id="acme")
    assert "customer=cus_real123" in seen["body"]


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

    assert SlackClient("xoxb-test", client=_client("https://slack.com/api", ok)).send_message("#c", "hi")["ok"] is True

    def bad(req):
        return httpx.Response(200, json={"ok": False, "error": "not_in_channel"})

    import pytest
    from app.integrations.clients import SlackAuthError
    with pytest.raises(SlackAuthError):
        SlackClient("xoxb-test", client=_client("https://slack.com/api", bad)).send_message("#c", "hi")


def test_clickup_create_task():
    def handler(req):
        assert str(req.url).endswith("/list/L1/task")
        return httpx.Response(200, json={"id": "task1"})

    out = ClickUpClient("pk-test", client=_client("https://api.clickup.com/api/v2", handler)).create_task("L1", "N", "D")
    assert out["id"] == "task1"


def test_calendly_available_slots():
    def handler(req):
        return httpx.Response(200, json={"collection": [{"start_time": "2026-07-10T10:00:00Z"}]})

    slots = CalendlyClient("cal-test", client=_client("https://api.calendly.com", handler)).available_slots("et1")
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


def test_ga4_property_id_strips_properties_prefix():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={
            "dimensionHeaders": [{"name": "pagePath"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [],
        })

    GA4Client(property_id="properties/123", client=_client("https://analyticsdata.googleapis.com/v1beta", handler)).run_report(
        "2026-07-01", "2026-07-07", ["sessions"], ["pagePath"])
    assert seen["url"].endswith("/properties/123:runReport")


def test_ga4_property_id_rejects_measurement_id():
    import pytest

    def handler(req):
        return httpx.Response(200, json={"dimensionHeaders": [], "metricHeaders": [], "rows": []})

    client = GA4Client(property_id="G-ABC123", client=_client("https://analyticsdata.googleapis.com/v1beta", handler))
    with pytest.raises(ValueError, match="Measurement ID"):
        client.run_report("2026-07-01", "2026-07-07", ["sessions"], ["pagePath"])


def _sf_mock(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_salesforce_test_connection_fetches_token_then_calls_data_endpoint():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if req.url.path == "/services/oauth2/token":
            body = req.content.decode()
            assert "grant_type=client_credentials" in body and "client_id=cid1" in body
            return httpx.Response(200, json={"access_token": "tok123"})
        assert req.headers["Authorization"] == "Bearer tok123"
        return httpx.Response(200, json=[{"version": "59.0"}])

    c = SalesforceClient(client_id="cid1", client_secret="secret1",
                         instance_url="https://acme.my.salesforce.com", client=_sf_mock(handler))
    result = c.test_connection()
    assert result == {"ok": True, "versions": 1}
    assert calls[0].endswith("/services/oauth2/token")
    assert calls[1].endswith("/services/data/")


def test_salesforce_test_connection_raises_on_bad_credentials():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_client"})

    c = SalesforceClient(client_id="cid1", client_secret="wrong",
                         instance_url="https://acme.my.salesforce.com", client=_sf_mock(handler))
    with pytest.raises(SalesforceAuthError):
        c.test_connection()


def test_salesforce_create_lead_sends_required_fields():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/services/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok123"})
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(201, json={"id": "00Q1", "success": True})

    c = SalesforceClient(client_id="cid1", client_secret="secret1",
                         instance_url="https://acme.my.salesforce.com/", client=_sf_mock(handler))
    result = c.create_lead(last_name="Jane Doe", company="Acme Inc", email="jane@acme.com", phone="555-1234")
    assert result["id"] == "00Q1"
    assert seen["url"].endswith("/services/data/v59.0/sobjects/Lead")
    assert seen["body"] == {"LastName": "Jane Doe", "Company": "Acme Inc", "Email": "jane@acme.com", "Phone": "555-1234"}


def test_salesforce_create_lead_raises_on_failure():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/services/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok123"})
        return httpx.Response(400, json=[{"message": "Required fields are missing"}])

    c = SalesforceClient(client_id="cid1", client_secret="secret1",
                         instance_url="https://acme.my.salesforce.com", client=_sf_mock(handler))
    with pytest.raises(SalesforceAuthError):
        c.create_lead(last_name="", company="Acme")


def test_gmail_smtp_client_uses_verified_tls_before_login(monkeypatch):
    """The App Password must only ever cross a certificate-verified TLS channel: assert starttls runs
    BEFORE login, with a default (verifying) SSL context, and that the message is actually sent."""
    import smtplib
    import ssl

    from app.integrations.clients import GmailSmtpClient

    order: list[str] = []
    seen: dict = {}

    class Smtp:
        def __init__(self, host, port, timeout=None):
            seen["host"], seen["port"], seen["timeout"] = host, port, timeout

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def starttls(self, context=None):
            order.append("starttls")
            seen["context"] = context

        def login(self, user, password):
            order.append("login")
            seen["user"], seen["password"] = user, password

        def send_message(self, message):
            order.append("send")
            seen["message"] = message

        def noop(self):
            order.append("noop")

    monkeypatch.setattr("smtplib.SMTP", Smtp)
    client = GmailSmtpClient(address="sales" + "@" + "acme.invalid", app_password="app-pw")
    assert client.send("to" + "@" + "acme.invalid", "Subject", "Body") == {
        "sent": True, "to": "to" + "@" + "acme.invalid"}
    assert order == ["starttls", "login", "send"]          # never login before TLS
    assert seen["host"] == "smtp.gmail.com" and seen["port"] == 587 and seen["timeout"]
    assert isinstance(seen["context"], ssl.SSLContext)
    assert seen["context"].verify_mode == ssl.CERT_REQUIRED
    assert seen["context"].check_hostname is True
    assert seen["user"] == "sales" + "@" + "acme.invalid" and seen["password"] == "app-pw"
    assert client.test_connection()["ok"] is True

    class BadAuth(Smtp):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad app password")

    import pytest

    from app.integrations.clients import GmailSmtpError

    monkeypatch.setattr("smtplib.SMTP", BadAuth)
    with pytest.raises(GmailSmtpError) as sent_err:
        client.send("to" + "@" + "acme.invalid", "S", "B")
    assert "reconnect" in str(sent_err.value)              # tells the operator what to do
    with pytest.raises(GmailSmtpError):
        client.test_connection()

    class Unreachable(Smtp):
        def __init__(self, host, port, timeout=None):
            raise OSError("dns failure")

    monkeypatch.setattr("smtplib.SMTP", Unreachable)
    with pytest.raises(GmailSmtpError):
        client.test_connection()


def test_slack_test_connection_reports_team_and_rejects_a_bad_token():
    import pytest

    from app.integrations.clients import SlackAuthError, SlackClient

    def ok(req):
        assert str(req.url).endswith("/auth.test")
        return httpx.Response(200, json={"ok": True, "team": "Acme", "user": "qiko-bot"})

    out = SlackClient("xoxb-t", client=_client("https://slack.com/api", ok)).test_connection()
    assert out == {"ok": True, "team": "Acme", "user": "qiko-bot"}

    def bad(req):
        return httpx.Response(200, json={"ok": False, "error": "invalid_auth"})

    with pytest.raises(SlackAuthError):
        SlackClient("xoxb-t", client=_client("https://slack.com/api", bad)).test_connection()
