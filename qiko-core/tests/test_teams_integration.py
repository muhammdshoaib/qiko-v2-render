"""Microsoft Teams Integration: connect/disconnect a per-tenant Incoming Webhook, send a test
notification, and the real trigger wired into RFP outcome recording (Win/Loss Analysis)."""
import asyncio

from app.modules.agents.service import Agent

from tests.helpers import auth_cookies

C = auth_cookies("teamsco", "owner")


def _seed_worker(client, tenant: str, worker_id: str = "w1") -> None:
    if asyncio.run(client.app.state.agents.get(tenant, worker_id)) is None:
        asyncio.run(client.app.state.agents.store.add(
            Agent(id=worker_id, tenant=tenant, name="Worker")))


class _FakeGateway:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, webhook_url: str, text: str) -> None:
        self.sent.append((webhook_url, text))


class _FailingGateway:
    def send(self, webhook_url: str, text: str) -> None:
        raise RuntimeError("Teams is down")


def test_webhook_status_defaults_to_disconnected(client):
    assert client.get("/api/v1/channels/teams/webhook", cookies=C).json() == {
        "connected": False, "connected_at": None,
    }


def test_webhook_connect_disconnect_and_test(client):
    _seed_worker(client, "teamsco")
    fake = _FakeGateway()
    client.app.state.teams_notifier.gateway = fake

    r = client.put("/api/v1/channels/teams/webhook",
                   json={"webhook_url": "https://outlook.office.com/webhook/abc"}, cookies=C)
    assert r.status_code == 200 and r.json()["connected"] is True

    status = client.get("/api/v1/channels/teams/webhook", cookies=C).json()
    assert status["connected"] is True and status["connected_at"]

    test = client.post("/api/v1/channels/teams/test", json={"worker": "w1"}, cookies=C)
    assert test.status_code == 200 and test.json()["sent"] is True
    assert fake.sent and fake.sent[0][0] == "https://outlook.office.com/webhook/abc"

    client.delete("/api/v1/channels/teams/webhook", cookies=C)
    assert client.get("/api/v1/channels/teams/webhook", cookies=C).json()["connected"] is False


def test_webhook_connect_rejects_non_https_url(client):
    r = client.put("/api/v1/channels/teams/webhook", json={"webhook_url": "http://not-secure.example"}, cookies=C)
    assert r.status_code == 422


def test_webhook_connect_rejects_non_teams_hosts_ssrf(client):
    # SSRF guard (OWASP A01/API7): an https:// URL is not enough -- it must be a genuine Microsoft
    # Teams webhook host, so an editor can't point the server-side POST at internal infrastructure.
    fake = _FakeGateway()
    client.app.state.teams_notifier.gateway = fake
    for bad in (
        "https://169.254.169.254/latest/meta-data/",   # cloud metadata endpoint
        "https://localhost/webhook",
        "https://internal-service.svc.cluster.local/hook",
        "https://evil.example.com/webhook",             # attacker-controlled host
        "https://outlook.office.com.evil.com/webhook",  # suffix-spoofing attempt
    ):
        r = client.put("/api/v1/channels/teams/webhook", json={"webhook_url": bad}, cookies=C)
        assert r.status_code == 422, bad
    # and nothing was ever sent to a rejected URL
    assert fake.sent == []


def test_webhook_connect_accepts_teams_workflow_host(client):
    # Modern Teams "Workflows" webhooks live on *.webhook.office.com / *.logic.azure.com.
    for good in (
        "https://acme.webhook.office.com/webhookb2/abc",
        "https://prod-12.westeurope.logic.azure.com/workflows/xyz/triggers/manual/paths/invoke",
    ):
        r = client.put("/api/v1/channels/teams/webhook", json={"webhook_url": good}, cookies=C)
        assert r.status_code == 200, good
        assert r.json()["connected"] is True


def test_webhook_test_without_a_connection_404s_as_422(client):
    _seed_worker(client, "teamsco2", "w2")
    r = client.post(
        "/api/v1/channels/teams/test", json={"worker": "w2"},
        cookies=auth_cookies("teamsco2", "owner"))
    assert r.status_code == 422


def test_webhook_test_surfaces_gateway_failure_as_502(client):
    _seed_worker(client, "teamsco")
    client.app.state.teams_notifier.gateway = _FailingGateway()
    client.put("/api/v1/channels/teams/webhook",
              json={"webhook_url": "https://outlook.office.com/webhook/xyz"}, cookies=C)
    r = client.post("/api/v1/channels/teams/test", json={"worker": "w1"}, cookies=C)
    assert r.status_code == 502


def test_webhook_writes_require_editor_role(client):
    viewer = auth_cookies("teamsco3", "viewer")
    assert client.put("/api/v1/channels/teams/webhook", json={"webhook_url": "https://x.example"},
                      cookies=viewer).status_code == 403
    assert client.delete("/api/v1/channels/teams/webhook", cookies=viewer).status_code == 403
    assert client.post("/api/v1/channels/teams/test", json={"worker": "w1"}, cookies=viewer).status_code == 403


def test_webhook_is_tenant_scoped(client):
    c1 = auth_cookies("teamst1", "owner")
    c2 = auth_cookies("teamst2", "owner")
    client.put("/api/v1/channels/teams/webhook", json={"webhook_url": "https://outlook.office.com/webhook/t1"},
              cookies=c1)
    assert client.get("/api/v1/channels/teams/webhook", cookies=c1).json()["connected"] is True
    assert client.get("/api/v1/channels/teams/webhook", cookies=c2).json()["connected"] is False


def test_recording_a_tender_outcome_notifies_teams(client):
    fake = _FakeGateway()
    client.app.state.teams_notifier.gateway = fake
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="w1", tenant="teamswl", name="Worker")))
    c = auth_cookies("teamswl", "owner")
    client.put("/api/v1/channels/teams/webhook",
              json={"webhook_url": "https://outlook.office.com/webhook/wl"}, cookies=c)

    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Big Tender"}, cookies=c).json()
    r = client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", json={"outcome": "won", "value": 12345}, cookies=c)
    assert r.status_code == 200
    assert any("Big Tender" in text and "won" in text.lower() for _url, text in fake.sent)

    r2 = client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", json={"outcome": "lost", "reason": "price"}, cookies=c)
    assert r2.status_code == 200
    assert any("lost" in text.lower() and "price" in text for _url, text in fake.sent)


def test_recording_outcome_without_teams_connected_still_succeeds(client):
    # notify() is best-effort -- no webhook configured must never break the actual outcome write.
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="w1", tenant="teamswl2", name="Worker")))
    c = auth_cookies("teamswl2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    r = client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", json={"outcome": "won"}, cookies=c)
    assert r.status_code == 200 and r.json()["outcome"] == "won"
