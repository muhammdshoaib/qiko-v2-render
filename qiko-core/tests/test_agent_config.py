from tests.helpers import auth_cookies


def test_update_agent_config_merges_and_persists(client):
    c = auth_cookies("configco", "owner")
    created = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()

    r1 = client.put(f"/api/v1/agents/{created['id']}/config", cookies=c,
                    json={"patch": {"expertise": "RFP writer", "tone": "professional"}})
    assert r1.status_code == 200
    assert r1.json()["config"] == {"expertise": "RFP writer", "tone": "professional"}

    r2 = client.put(f"/api/v1/agents/{created['id']}/config", cookies=c,
                    json={"patch": {"target_audience": "Pre-sales team"}})
    assert r2.json()["config"] == {"expertise": "RFP writer", "tone": "professional",
                                    "target_audience": "Pre-sales team"}

    listed = client.get("/api/v1/agents", cookies=c).json()
    assert listed[0]["config"]["expertise"] == "RFP writer"


def test_list_agents_hides_archived_config(client):
    """Archiving is a reversible soft-hide: PUT config {"archived": true} drops the worker from
    GET /agents, and {"archived": false} brings it back. No hard delete."""
    c = auth_cookies("archco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "SI worker"}, cookies=c).json()
    assert [a["id"] for a in client.get("/api/v1/agents", cookies=c).json()] == [agent["id"]]

    # archive -> hidden from the list, but the row and its config are NOT deleted
    client.put(f"/api/v1/agents/{agent['id']}/config", cookies=c, json={"patch": {"archived": True}})
    assert client.get("/api/v1/agents", cookies=c).json() == []
    # still fetchable directly (proves it was hidden, not destroyed)
    assert client.get(f"/api/v1/agents/{agent['id']}/vapi-credentials", cookies=c).status_code == 200

    # reversible: un-archive restores it exactly
    client.put(f"/api/v1/agents/{agent['id']}/config", cookies=c, json={"patch": {"archived": False}})
    assert [a["id"] for a in client.get("/api/v1/agents", cookies=c).json()] == [agent["id"]]


def test_update_agent_config_404_for_missing_agent(client):
    c = auth_cookies("configco2", "owner")
    r = client.put("/api/v1/agents/missing/config", cookies=c, json={"patch": {"x": "y"}})
    assert r.status_code == 404


def test_update_agent_config_requires_editor_role(client):
    r = client.put("/api/v1/agents/x/config", cookies=auth_cookies("configco3", "viewer"),
                   json={"patch": {}})
    assert r.status_code == 403


def test_update_agent_config_rejects_ga4_credentials_added(client):
    """ga4_credentials_added must only ever be set by the dedicated
    POST /intelligence/agents/{id}/sources/ga4 endpoint, which records an audit row. Letting the
    generic merge-patch flip it directly would let an editor claim a GA4 connection with no audit
    trail at all (A09/A01) -- same protection every other <x>_credentials_added flag already has."""
    c = auth_cookies("configco4", "owner")
    agent = client.post("/api/v1/agents", json={"name": "GA4 worker"}, cookies=c).json()
    r = client.put(f"/api/v1/agents/{agent['id']}/config", cookies=c,
                   json={"patch": {"ga4_credentials_added": True}})
    assert r.status_code == 422
    assert "ga4_credentials_added" in r.json()["detail"]
