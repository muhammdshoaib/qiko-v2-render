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


def test_update_agent_config_404_for_missing_agent(client):
    c = auth_cookies("configco2", "owner")
    r = client.put("/api/v1/agents/missing/config", cookies=c, json={"patch": {"x": "y"}})
    assert r.status_code == 404


def test_update_agent_config_requires_editor_role(client):
    r = client.put("/api/v1/agents/x/config", cookies=auth_cookies("configco3", "viewer"),
                   json={"patch": {}})
    assert r.status_code == 403
