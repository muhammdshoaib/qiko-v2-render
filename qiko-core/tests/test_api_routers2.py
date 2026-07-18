"""Functional API tests for chat/teams/leads/billing/channels/excel/voice/signal routers (authenticated)."""
import base64

from tests.helpers import auth_cookies, bootstrap_admin

C = auth_cookies("acme", "owner")
ISO = "IDG holds a current ISO 9001 certification valid through 2027."


def test_chat_ask_is_grounded_and_records(client):
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=C)
    r = client.post("/api/v1/chat/ask", json={"conversation_id": "c1",
                    "question": "Describe your ISO 9001 certification.", "topic": "qms"}, cookies=C)
    assert r.status_code == 200 and r.json()["role"] == "assistant" and "ISO 9001" in r.json()["text"]
    hist = client.get("/api/v1/chat/history/c1", cookies=C).json()
    assert [m["role"] for m in hist] == ["user", "assistant"]


def test_teams_router(client):
    team = client.post("/api/v1/teams", json={"owner_id": "owner"}, cookies=C).json()
    tid = team["team_id"]
    add = client.post(f"/api/v1/teams/{tid}/members", json={"user_id": "u2", "role": "editor"}, cookies=C).json()
    assert add["members"]["u2"] == "editor"
    assert client.post(f"/api/v1/teams/{tid}/members", json={"user_id": "u3", "role": "owner"}, cookies=C).status_code == 400


def test_teams_router_blocks_cross_tenant_access(client):
    # BOLA regression guard: another tenant must not be able to read or mutate acme's team just
    # by guessing/observing its team_id -- every team_id-scoped route must 404 for an outsider.
    team = client.post("/api/v1/teams", json={"owner_id": "owner"}, cookies=C).json()
    tid = team["team_id"]
    other = auth_cookies("globex", "admin")

    assert client.get(f"/api/v1/teams/{tid}/members", cookies=other).status_code == 404
    assert client.post(f"/api/v1/teams/{tid}/members", json={"user_id": "mallory", "role": "admin"},
                       cookies=other).status_code == 404
    assert client.put(f"/api/v1/teams/{tid}/members/owner", json={"role": "viewer"}, cookies=other).status_code == 404
    assert client.delete(f"/api/v1/teams/{tid}/members/owner", cookies=other).status_code == 404
    assert client.post(f"/api/v1/teams/{tid}/invites", json={"email": "mallory@evil.com"},
                       cookies=other).status_code == 404

    # acme's own admin still works against its own team
    assert client.get(f"/api/v1/teams/{tid}/members", cookies=C).status_code == 200


def test_teams_router_requires_admin_for_create_and_add_member(client):
    # RBAC regression guard: a viewer must not be able to create a team or add members (incl.
    # escalating someone to owner) -- create_team/add_member are admin-gated like the other
    # mutating team endpoints.
    viewer = auth_cookies("acme", "viewer")
    assert client.post("/api/v1/teams", json={"owner_id": "owner"}, cookies=viewer).status_code == 403

    # an admin can set the team up; the viewer still cannot add members to it.
    tid = client.post("/api/v1/teams", json={"owner_id": "owner"}, cookies=C).json()["team_id"]
    assert client.post(f"/api/v1/teams/{tid}/members", json={"user_id": "u2", "role": "editor"},
                       cookies=viewer).status_code == 403


def test_leads_router(client):
    ok = client.post("/api/v1/leads", json={"kind": "enterprise", "name": "Acme", "email": "b@acme.com"}, cookies=C)
    assert ok.status_code == 200 and ok.json()["kind"] == "enterprise"
    assert client.post("/api/v1/leads", json={"kind": "spam", "name": "x", "email": "b@x.com"}, cookies=C).status_code == 400


def test_checkout_and_portal_convert_gateway_failures_to_502():
    """A real gateway (Stripe/...) blowing up must surface as a clean 502, not a raw 500."""
    import httpx
    import pytest
    from fastapi import HTTPException

    from app.modules.billing.router import CheckoutBody, checkout, portal
    from app.modules.billing.subscriptions import SubscriptionService

    class FailingGateway:
        def create_checkout_session(self, **_kw):
            raise httpx.HTTPStatusError("boom", request=httpx.Request("POST", "https://x"),
                                        response=httpx.Response(400))

        def billing_portal_url(self, **_kw):
            raise httpx.HTTPStatusError("boom", request=httpx.Request("POST", "https://x"),
                                        response=httpx.Response(400))

    subs = SubscriptionService(FailingGateway())
    with pytest.raises(HTTPException) as e1:
        checkout(CheckoutBody(plan="pro"), tenant="t", subs=subs)
    assert e1.value.status_code == 502

    with pytest.raises(HTTPException) as e2:
        portal(tenant="t", subs=subs)
    assert e2.value.status_code == 502


def test_billing_webhook_public_and_subscription(client):
    # webhook is public (signature-verified in prod), no auth cookie
    evt = {"id": "evt1", "type": "invoice.paid",
           "data": {"object": {"id": "in1", "customer": "cus1", "amount_paid": 5000, "status": "paid"}}}
    assert client.post("/api/v1/billing/webhook/stripe", json=evt).json()["action"] == "invoice_synced"
    # Subscription subject is the authed tenant ("acme" for C), not a client-supplied id.
    client.post("/api/v1/billing/subscription/activate", json={"plan": "pro"}, cookies=C)
    assert client.get("/api/v1/billing/subscription", cookies=C).json()["status"] == "active"


def test_billing_webhook_checkout_links_tenant_and_activates(client):
    # checkout.session.completed carries client_reference_id (our tenant) + the real Stripe
    # customer id; the handler links them and activates the tenant's subscription server-side.
    evt = {"id": "evt_ck1", "type": "checkout.session.completed",
           "data": {"object": {"id": "cs_1", "customer": "cus_live_1",
                                "client_reference_id": "acme", "metadata": {"plan": "pro"}}}}
    assert client.post("/api/v1/billing/webhook/stripe", json=evt).json()["action"] == "subscription_activated"
    assert client.get("/api/v1/billing/subscription", cookies=C).json()["status"] == "active"


def test_channels_whatsapp_public(client):
    assert client.get("/api/v1/channels/whatsapp/webhook",
                      params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "123"}).status_code == 403
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"id": "wamid.1", "from": "155", "type": "text", "text": {"body": "hi"}}]}}]}]}
    assert client.post("/api/v1/channels/whatsapp/webhook", json=payload).json()["processed"] == ["wamid.1"]


def test_excel_search(client):
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "excel-q3-0", "text": "region: EMEA, revenue: 120000"}, cookies=C)
    hits = client.post("/api/v1/excel/search", json={"query": "EMEA revenue"}, cookies=C).json()["results"]
    assert any("EMEA" in h for h in hits)


def test_voice_speak(client):
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=C)
    audio = base64.b64encode(b"Tell me about your ISO 9001 certification").decode()
    r = client.post("/api/v1/voice/speak", json={"conversation_id": "v1", "audio_b64": audio}, cookies=C).json()
    assert "ISO 9001" in r["answer"] and r["audio_b64"]


def test_signal_router(client):
    proj = client.post("/api/v1/signal/projects", json={"brand": "IDG", "domain": "idg.example"}, cookies=C).json()
    scan = client.post("/api/v1/signal/scan", json={"project_id": proj["project_id"]}, cookies=C).json()
    assert client.get(f"/api/v1/signal/score/{scan['scan_id']}", cookies=C).status_code == 200


def test_admin_customers_requires_admin(client):
    # a regular tenant user -- even a tenant "admin"/"owner" -- is not a platform admin
    assert client.get("/api/v1/admin/customers", cookies=auth_cookies("t", "viewer")).status_code == 403
    assert client.get("/api/v1/admin/customers", cookies=auth_cookies("t", "admin")).status_code == 403

    admin_email = "platform-admin2@qiko.ai"
    bootstrap_admin(client, admin_email)
    body = client.get("/api/v1/admin/customers", cookies=auth_cookies("t", "viewer", email=admin_email)).json()
    assert body["total"] == 0


def test_admin_overview_and_analytics(client):
    admin_email = "platform-admin3@qiko.ai"
    bootstrap_admin(client, admin_email)
    admin_cookies = auth_cookies("t", "viewer", email=admin_email)

    ov = client.get("/api/v1/admin/overview", cookies=admin_cookies).json()
    assert ov["customers_total"] == 0 and ov["active_subscriptions"] == 0 and ov["by_plan"] == {}
    an = client.get("/api/v1/admin/analytics", cookies=admin_cookies).json()
    assert an["had_data"] is False and an["sessions"] == 0
    # a regular tenant admin/owner is blocked -- only a real platform admin gets in
    assert client.get("/api/v1/admin/overview", cookies=auth_cookies("t", "admin")).status_code == 403
