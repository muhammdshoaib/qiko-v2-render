"""Tests for the self-service worker API key (POST/GET/DELETE /agents/{id}/worker-api-key)."""

from tests.helpers import auth_cookies


def test_generate_returns_the_plaintext_key_once_and_marks_configured(client):
    c = auth_cookies("wakco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()

    response = client.post(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c)

    assert response.status_code == 200
    body = response.json()
    assert len(body["api_key"]) > 20
    assert body["configured"] is True
    assert body["generated_at"] is not None


def test_get_status_never_returns_the_plaintext_key(client):
    c = auth_cookies("wakco2", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c)

    response = client.get(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c)

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert "api_key" not in body


def test_get_status_before_generation_reports_not_configured(client):
    c = auth_cookies("wakco3", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()

    response = client.get(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c)

    assert response.status_code == 200
    assert response.json() == {"configured": False, "generated_at": None}


def test_regenerating_produces_a_new_key_and_invalidates_the_old_one(client):
    c = auth_cookies("wakco4", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()

    first = client.post(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c).json()
    second = client.post(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c).json()

    assert first["api_key"] != second["api_key"]


def test_revoke_clears_the_key(client):
    c = auth_cookies("wakco5", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c)

    response = client.delete(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c)

    assert response.status_code == 200
    assert response.json() == {"configured": False, "generated_at": None}


def test_generate_requires_editor_role(client):
    c = auth_cookies("wakco6", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()
    viewer = auth_cookies("wakco6", "viewer")

    response = client.post(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=viewer)

    assert response.status_code == 403


def test_generate_404s_for_a_missing_agent(client):
    c = auth_cookies("wakco7", "owner")
    response = client.post("/api/v1/agents/does-not-exist/worker-api-key", cookies=c)
    assert response.status_code == 404


def test_worker_api_key_hash_never_leaks_through_the_generic_agent_list(client):
    c = auth_cookies("wakco8", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/worker-api-key", cookies=c)

    listed = client.get("/api/v1/agents", cookies=c).json()

    assert "worker_api_key_hash" not in listed[0]["config"]


def test_worker_api_key_hash_cannot_be_set_through_the_generic_config_patch(client):
    c = auth_cookies("wakco9", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()

    response = client.put(f"/api/v1/agents/{agent['id']}/config", cookies=c,
                          json={"patch": {"worker_api_key_hash": "not-a-real-hash"}})

    assert response.status_code == 422
