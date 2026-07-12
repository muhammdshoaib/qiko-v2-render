"""Microsoft Teams Integration: connect/disconnect a per-tenant Incoming Webhook, send a test
notification, and the real trigger wired into RFP outcome recording (Win/Loss Analysis)."""
from tests.helpers import auth_cookies

C = auth_cookies("teamsco", "owner")


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
    fake = _FakeGateway()
    client.app.state.teams_notifier.gateway = fake

    r = client.put("/api/v1/channels/teams/webhook",
                   json={"webhook_url": "https://outlook.office.com/webhook/abc"}, cookies=C)
    assert r.status_code == 200 and r.json()["connected"] is True

    status = client.get("/api/v1/channels/teams/webhook", cookies=C).json()
    assert status["connected"] is True and status["connected_at"]

    test = client.post("/api/v1/channels/teams/test", cookies=C)
    assert test.status_code == 200 and test.json()["sent"] is True
    assert fake.sent and fake.sent[0][0] == "https://outlook.office.com/webhook/abc"

    client.delete("/api/v1/channels/teams/webhook", cookies=C)
    assert client.get("/api/v1/channels/teams/webhook", cookies=C).json()["connected"] is False


def test_webhook_connect_rejects_non_https_url(client):
    r = client.put("/api/v1/channels/teams/webhook", json={"webhook_url": "http://not-secure.example"}, cookies=C)
    assert r.status_code == 422


def test_webhook_test_without_a_connection_404s_as_422(client):
    r = client.post("/api/v1/channels/teams/test", cookies=auth_cookies("teamsco2", "owner"))
    assert r.status_code == 422


def test_webhook_test_surfaces_gateway_failure_as_502(client):
    client.app.state.teams_notifier.gateway = _FailingGateway()
    client.put("/api/v1/channels/teams/webhook",
              json={"webhook_url": "https://outlook.office.com/webhook/xyz"}, cookies=C)
    r = client.post("/api/v1/channels/teams/test", cookies=C)
    assert r.status_code == 502


def test_webhook_writes_require_editor_role(client):
    viewer = auth_cookies("teamsco3", "viewer")
    assert client.put("/api/v1/channels/teams/webhook", json={"webhook_url": "https://x.example"},
                      cookies=viewer).status_code == 403
    assert client.delete("/api/v1/channels/teams/webhook", cookies=viewer).status_code == 403
    assert client.post("/api/v1/channels/teams/test", cookies=viewer).status_code == 403


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
    c = auth_cookies("teamswl2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    r = client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", json={"outcome": "won"}, cookies=c)
    assert r.status_code == 200 and r.json()["outcome"] == "won"
