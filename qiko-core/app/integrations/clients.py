"""Concrete integration clients behind the domain gateway protocols.

Each client takes an injectable ``httpx.Client`` so request construction (URL, method, auth, body)
is unit-testable with ``httpx.MockTransport`` and no network. In prod the default client is built
from configured secrets (loaded via SSM). Live/credentialed integration testing happens later.
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings


def _client(base_url: str, headers: dict[str, str], client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(base_url=base_url, headers=headers, timeout=15.0)


class StripeClient:
    """Implements StripeGateway + PaymentLinkGateway (form-encoded Stripe REST API)."""

    def __init__(self, secret_key: str | None = None, client: httpx.Client | None = None):
        key = secret_key or get_settings().stripe_secret_key
        self._c = _client("https://api.stripe.com/v1", {"Authorization": f"Bearer {key}"}, client)

    def create_checkout_session(self, *, customer_id: str, price_id: str, promo: str | None = None) -> str:
        base = get_settings().public_base_url
        data = {"mode": "subscription", "customer": customer_id,
                "line_items[0][price]": price_id, "line_items[0][quantity]": "1",
                "success_url": f"{base}/checkout/success", "cancel_url": f"{base}/checkout/cancel"}
        if promo:
            data["discounts[0][promotion_code]"] = promo
        r = self._c.post("/checkout/sessions", data=data)
        r.raise_for_status()
        return r.json()["url"]

    def billing_portal_url(self, *, customer_id: str) -> str:
        r = self._c.post("/billing_portal/sessions", data={"customer": customer_id})
        r.raise_for_status()
        return r.json()["url"]

    def create_payment_link(self, *, amount_cents: int, session_id: str, recurring: bool) -> str:
        data = {"line_items[0][price_data][currency]": "usd",
                "line_items[0][price_data][unit_amount]": str(amount_cents),
                "line_items[0][price_data][product_data][name]": f"Invoice {session_id}",
                "line_items[0][quantity]": "1"}
        r = self._c.post("/payment_links", data=data)
        r.raise_for_status()
        return r.json()["url"]


class WhatsAppClient:
    """Implements WhatsAppGateway via the Meta Graph API."""

    def __init__(self, access_token: str | None = None, phone_number_id: str | None = None,
                 client: httpx.Client | None = None):
        s = get_settings()
        self._phone = phone_number_id or s.whatsapp_phone_number_id
        token = access_token or s.whatsapp_access_token
        self._c = _client("https://graph.facebook.com/v21.0", {"Authorization": f"Bearer {token}"}, client)

    def send_text(self, to: str, text: str) -> dict:
        r = self._c.post(f"/{self._phone}/messages",
                         json={"messaging_product": "whatsapp", "to": to,
                               "type": "text", "text": {"body": text}})
        r.raise_for_status()
        return r.json()


class SlackClient:
    """Implements SlackGateway via chat.postMessage."""

    def __init__(self, bot_token: str | None = None, client: httpx.Client | None = None):
        token = bot_token or get_settings().slack_bot_token
        self._c = _client("https://slack.com/api", {"Authorization": f"Bearer {token}"}, client)

    def send_message(self, channel: str, text: str) -> dict:
        r = self._c.post("/chat.postMessage", json={"channel": channel, "text": text})
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            raise RuntimeError(f"slack error: {body.get('error')}")
        return body


class ClickUpClient:
    """Implements ClickUpGateway (create task in a list)."""

    def __init__(self, api_token: str | None = None, client: httpx.Client | None = None):
        token = api_token or get_settings().clickup_api_token
        self._c = _client("https://api.clickup.com/api/v2", {"Authorization": token}, client)

    def create_task(self, list_id: str, name: str, description: str) -> dict:
        r = self._c.post(f"/list/{list_id}/task", json={"name": name, "description": description})
        r.raise_for_status()
        return r.json()


class CalendlyClient:
    """Implements CalendlyGateway (Calendly API v2)."""

    def __init__(self, token: str | None = None, client: httpx.Client | None = None):
        tok = token or get_settings().calendly_token
        self._c = _client("https://api.calendly.com", {"Authorization": f"Bearer {tok}"}, client)

    def available_slots(self, event_type: str) -> list[str]:
        r = self._c.get("/event_type_available_times", params={"event_type": event_type})
        r.raise_for_status()
        return [s["start_time"] for s in r.json().get("collection", [])]

    def create_booking(self, event_type: str, invitee_email: str, start: str) -> dict:
        r = self._c.post("/scheduled_events",
                         json={"event_type": event_type, "invitee": {"email": invitee_email}, "start_time": start})
        r.raise_for_status()
        return r.json()


class SignalEngineClient:
    """Implements SignalEngineGateway (thothgraph/qiko-signal engine HTTP API)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 client: httpx.Client | None = None):
        s = get_settings()
        self._c = _client(base_url or s.signal_engine_url,
                          {"Authorization": f"Bearer {api_key or s.signal_engine_api_key}"}, client)

    def create_project(self, tenant: str, brand: str, domain: str) -> dict:
        r = self._c.post("/projects", json={"tenant": tenant, "brand": brand, "domain": domain})
        r.raise_for_status()
        return r.json()

    def run_scan(self, project_id: str) -> dict:
        r = self._c.post("/scans", json={"project_id": project_id})
        r.raise_for_status()
        return r.json()

    def get_score(self, scan_id: str) -> dict:
        r = self._c.get(f"/scans/{scan_id}/score")
        r.raise_for_status()
        return r.json()

    def get_buckets(self, scan_id: str) -> dict:
        r = self._c.get(f"/scans/{scan_id}/buckets")
        r.raise_for_status()
        return r.json()

    def get_recommendations(self, scan_id: str) -> list[dict]:
        r = self._c.get(f"/scans/{scan_id}/recommendations")
        r.raise_for_status()
        return r.json()

    def export_pdf(self, scan_id: str) -> str:
        r = self._c.post(f"/scans/{scan_id}/export")
        r.raise_for_status()
        return r.json()["url"]


class GA4Client:
    """Implements GA4Gateway via the Analytics Data API v1beta runReport."""

    def __init__(self, property_id: str | None = None, access_token: str | None = None,
                 client: httpx.Client | None = None):
        s = get_settings()
        self._property = property_id or s.ga4_property_id
        token = access_token or s.ga4_access_token
        self._c = _client("https://analyticsdata.googleapis.com/v1beta",
                          {"Authorization": f"Bearer {token}"}, client)

    def run_report(self, start: str, end: str, metrics: list[str], dimensions: list[str]) -> list[dict]:
        body = {"dateRanges": [{"startDate": start, "endDate": end}],
                "metrics": [{"name": m} for m in metrics],
                "dimensions": [{"name": d} for d in dimensions]}
        r = self._c.post(f"/properties/{self._property}:runReport", json=body)
        r.raise_for_status()
        payload = r.json()
        dim_names = [d["name"] for d in payload.get("dimensionHeaders", [])]
        met_names = [m["name"] for m in payload.get("metricHeaders", [])]
        rows: list[dict] = []
        for row in payload.get("rows", []):
            record = {dim_names[i]: v["value"] for i, v in enumerate(row.get("dimensionValues", []))}
            record.update({met_names[i]: v["value"] for i, v in enumerate(row.get("metricValues", []))})
            rows.append(record)
        return rows
