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

    def create_checkout_session(self, *, customer_id: str, price_id: str, promo: str | None = None,
                                client_reference_id: str | None = None, plan: str | None = None) -> str:
        base = get_settings().public_base_url
        data = {"mode": "subscription",
                "line_items[0][price]": price_id, "line_items[0][quantity]": "1",
                "success_url": f"{base}/checkout/success", "cancel_url": f"{base}/checkout/cancel"}
        # Only pass `customer` when it is a REAL Stripe customer id ("cus_..."). Our `customer_id` is
        # the tenant string until a webhook links a real customer, and Stripe 400s on an unknown
        # customer. When absent, Checkout creates the customer and collects the email itself, and
        # `client_reference_id` still ties it back to our tenant on checkout.session.completed.
        if customer_id and customer_id.startswith("cus_"):
            data["customer"] = customer_id
        if promo:
            data["discounts[0][promotion_code]"] = promo
        if client_reference_id:
            # Ties the resulting Stripe customer back to our tenant on the webhook (server-side).
            data["client_reference_id"] = client_reference_id
        if plan:
            # Carry the internal plan on the session (and the resulting subscription) so the webhook
            # activates the correct plan instead of defaulting to "pro".
            data["metadata[plan]"] = plan
            data["subscription_data[metadata][plan]"] = plan
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


class TeamsWebhookClient:
    """Implements TeamsGateway via a Microsoft Teams Incoming Webhook connector. Unlike the other
    clients here, the URL isn't a fixed base_url from settings -- it's per-tenant (see
    channels.teams_integration) and passed to each call, so this client takes no constructor args."""

    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def send(self, webhook_url: str, text: str) -> None:
        c = self._client or httpx.Client(timeout=15.0)
        r = c.post(webhook_url, json={"text": text})
        r.raise_for_status()


class ClickUpAuthError(Exception):
    pass


class ClickUpClient:
    """Implements ClickUpGateway (create task in a list)."""

    def __init__(self, api_token: str, client: httpx.Client | None = None):
        # Required on purpose: there is no Qiko-owned ClickUp account to silently fall back to.
        self._c = _client("https://api.clickup.com/api/v2", {"Authorization": api_token}, client)

    def create_task(self, list_id: str, name: str, description: str) -> dict:
        r = self._c.post(f"/list/{list_id}/task", json={"name": name, "description": description})
        r.raise_for_status()
        return r.json()

    def test_connection(self) -> dict:
        """Cheapest authenticated call: who owns this token. Used by the Connections UI."""
        r = self._c.get("/user")
        if r.status_code in (401, 403):
            raise ClickUpAuthError("ClickUp rejected the API token")
        try:
            r.raise_for_status()
            user = (r.json() or {}).get("user") or {}
        except (httpx.HTTPError, ValueError) as e:
            raise ClickUpAuthError("ClickUp connection failed") from e
        return {"ok": True, "user": user.get("username") or user.get("email") or ""}


class CalendlyAuthError(Exception):
    pass


class CalendlyClient:
    """Implements CalendlyGateway (Calendly API v2)."""

    def __init__(self, token: str, client: httpx.Client | None = None):
        # Required on purpose: there is no Qiko-owned Calendly account to silently fall back to.
        self._c = _client("https://api.calendly.com", {"Authorization": f"Bearer {token}"}, client)

    def available_slots(self, event_type: str) -> list[str]:
        r = self._c.get("/event_type_available_times", params={"event_type": event_type})
        r.raise_for_status()
        return [s["start_time"] for s in r.json().get("collection", [])]

    def test_connection(self) -> dict:
        """Cheapest authenticated call: the token's own user. Used by the Connections UI."""
        r = self._c.get("/users/me")
        if r.status_code in (401, 403):
            raise CalendlyAuthError("Calendly rejected the access token")
        try:
            r.raise_for_status()
            resource = (r.json() or {}).get("resource") or {}
        except (httpx.HTTPError, ValueError) as e:
            raise CalendlyAuthError("Calendly connection failed") from e
        return {"ok": True, "user": resource.get("name") or resource.get("email") or ""}

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


class SalesforceAuthError(Exception):
    pass


class SalesforceClient:
    """Implements SalesforceGateway (app.modules.crm.salesforce).

    Deliberately the same "simplest real integration shape" as Calendly/ClickUp above, not a
    full authorization_code OAuth flow: each tenant creates their own Salesforce Connected App
    (Setup -> App Manager -> New Connected App, enable OAuth, "Client Credentials Flow") and
    pastes its client id/secret + their org's instance URL here -- exactly the same 3-value
    paste UX as the Vapi voice connection. Client Credentials is a server-to-server OAuth2 grant
    (no user redirect/consent screen), which is what a reusable, per-tenant integration needs;
    a full authorization_code flow would require Qiko itself to be a registered, security-reviewed
    ISV app in Salesforce's marketplace, which is a much bigger lift for the same outcome here."""

    def __init__(self, client_id: str, client_secret: str, instance_url: str, client: httpx.Client | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._instance_url = instance_url.rstrip("/")
        self._c = client or httpx.Client(timeout=15.0)

    def _access_token(self) -> str:
        r = self._c.post(f"{self._instance_url}/services/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": self._client_id, "client_secret": self._client_secret,
        })
        if r.status_code != 200:
            raise SalesforceAuthError(f"Salesforce token request failed: {r.status_code} {r.text}")
        return r.json()["access_token"]

    def test_connection(self) -> dict:
        """Verify the credentials by fetching a token and hitting the cheapest possible endpoint."""
        token = self._access_token()
        r = self._c.get(f"{self._instance_url}/services/data/", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return {"ok": True, "versions": len(r.json())}

    def create_lead(self, *, last_name: str, company: str, email: str | None = None,
                    phone: str | None = None, description: str | None = None) -> dict:
        """Push a CRM contact as a Salesforce Lead. `last_name` and `company` are the only two
        fields Salesforce's Lead object requires."""
        token = self._access_token()
        body = {"LastName": last_name or "Unknown", "Company": company}
        if email:
            body["Email"] = email
        if phone:
            body["Phone"] = phone
        if description:
            body["Description"] = description
        r = self._c.post(f"{self._instance_url}/services/data/v59.0/sobjects/Lead",
                         headers={"Authorization": f"Bearer {token}"}, json=body)
        if r.status_code != 201:
            raise SalesforceAuthError(f"Salesforce Lead creation failed: {r.status_code} {r.text}")
        return r.json()
