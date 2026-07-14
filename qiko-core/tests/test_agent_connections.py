from tests.helpers import auth_cookies


def test_vapi_credentials_save_and_masked_retrieve(client):
    c = auth_cookies("vapico", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()

    save = client.post(f"/api/v1/agents/{agent['id']}/vapi-credentials", cookies=c, json={
        "vapi_assistant_id": "asst-123", "vapi_public_key": "pk-abc", "vapi_api_key": "sk-supersecret",
    })
    assert save.status_code == 200
    body = save.json()
    assert body["vapi_credentials_added"] is True
    assert body["vapi_assistant_id"] == "asst-123"
    assert body["vapi_public_key"] == "pk-abc"
    # the real secret is never returned, before or after saving
    assert "sk-supersecret" not in save.text
    assert body["vapi_api_key_masked"] and body["vapi_api_key_masked"] != "sk-supersecret"

    fetched = client.get(f"/api/v1/agents/{agent['id']}/vapi-credentials", cookies=c).json()
    assert fetched["vapi_credentials_added"] is True
    assert "sk-supersecret" not in client.get(f"/api/v1/agents/{agent['id']}/vapi-credentials", cookies=c).text


def test_agents_list_and_get_never_leak_the_encrypted_vapi_blob(client):
    # The dedicated vapi-credentials endpoints only ever hand back a masked preview -- but the
    # generic Agent views (list, config patch, mark-ready, calendly update) return the same
    # free-form config dict, which is where vapi_api_key_encrypted actually lives once saved.
    # Those must redact it too: no legitimate client need ever reads the ciphertext from there.
    c = auth_cookies("vapico3", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/vapi-credentials", cookies=c, json={
        "vapi_assistant_id": "asst-123", "vapi_public_key": "pk-abc", "vapi_api_key": "sk-supersecret",
    })

    listed = client.get("/api/v1/agents", cookies=c)
    assert "vapi_api_key_encrypted" not in listed.text

    patched = client.put(f"/api/v1/agents/{agent['id']}/config", cookies=c, json={"patch": {"tone": "friendly"}})
    assert "vapi_api_key_encrypted" not in patched.text
    assert patched.json()["config"]["vapi_assistant_id"] == "asst-123"  # other config keys still round-trip

    ready = client.post(f"/api/v1/agents/{agent['id']}/ready", cookies=c)
    assert "vapi_api_key_encrypted" not in ready.text

    linked = client.put(f"/api/v1/agents/{agent['id']}/calendly-event-type", cookies=c,
                        json={"calendly_event_type": "https://calendly.com/foo/30min"})
    assert "vapi_api_key_encrypted" not in linked.text


def test_vapi_credentials_404_for_missing_agent(client):
    c = auth_cookies("vapico2", "owner")
    r = client.post("/api/v1/agents/missing/vapi-credentials", cookies=c, json={
        "vapi_assistant_id": "a", "vapi_public_key": "b", "vapi_api_key": "c",
    })
    assert r.status_code == 404


def test_calendly_event_type_update(client):
    c = auth_cookies("calco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()
    r = client.put(f"/api/v1/agents/{agent['id']}/calendly-event-type", cookies=c,
                   json={"calendly_event_type": "https://calendly.com/foo/30min"})
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["calendly_event_type"] == "https://calendly.com/foo/30min"
    assert body["config"]["calendly_is_linked"] is True


def test_connections_require_editor_role(client):
    c = auth_cookies("connco", "viewer")
    assert client.post("/api/v1/agents/x/vapi-credentials", cookies=c, json={
        "vapi_assistant_id": "a", "vapi_public_key": "b", "vapi_api_key": "c",
    }).status_code == 403
    assert client.put("/api/v1/agents/x/calendly-event-type", cookies=c,
                      json={"calendly_event_type": "y"}).status_code == 403


def test_salesforce_credentials_save_and_masked_retrieve(client):
    c = auth_cookies("sfco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG Sales"}, cookies=c).json()

    save = client.post(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c, json={
        "client_id": "3MVG9...client", "client_secret": "supersecret", "instance_url": "https://acme.my.salesforce.com",
    })
    assert save.status_code == 200
    body = save.json()
    assert body["salesforce_credentials_added"] is True
    assert body["instance_url"] == "https://acme.my.salesforce.com"
    assert "supersecret" not in save.text
    assert body["client_id_masked"] and body["client_id_masked"] != "3MVG9...client"

    fetched = client.get(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c)
    assert fetched.status_code == 200 and fetched.json()["salesforce_credentials_added"] is True
    assert "supersecret" not in fetched.text

    listed = client.get("/api/v1/agents", cookies=c)
    assert "salesforce_client_secret_encrypted" not in listed.text


def test_salesforce_credentials_rejects_non_https_instance_url(client):
    c = auth_cookies("sfco2", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()
    r = client.post(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c, json={
        "client_id": "cid", "client_secret": "secret", "instance_url": "http://not-https.example.com",
    })
    assert r.status_code == 422


def test_salesforce_credentials_rejects_non_salesforce_host_ssrf(client):
    # SSRF guard (OWASP A01/API7): the stored instance_url receives the tenant's own client
    # secret on the token call, so an https:// URL alone isn't enough -- it must be a Salesforce
    # host, not an internal/attacker-controlled one.
    c = auth_cookies("sfcossrf", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()
    for bad in (
        "https://169.254.169.254/",
        "https://localhost/services/oauth2/token",
        "https://evil.example.com",
        "https://acme.my.salesforce.com.evil.com",  # suffix-spoofing attempt
    ):
        r = client.post(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c, json={
            "client_id": "cid", "client_secret": "secret", "instance_url": bad,
        })
        assert r.status_code == 422, bad


def test_salesforce_disconnect_clears_credentials(client):
    c = auth_cookies("sfco3", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c, json={
        "client_id": "cid", "client_secret": "secret", "instance_url": "https://acme.my.salesforce.com",
    })

    disconnected = client.delete(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c)
    assert disconnected.status_code == 200 and disconnected.json()["disconnected"] is True

    fetched = client.get(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c).json()
    assert fetched["salesforce_credentials_added"] is False and fetched["instance_url"] == ""


def test_salesforce_test_connection_requires_credentials_first(client):
    c = auth_cookies("sfco4", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()
    r = client.post(f"/api/v1/agents/{agent['id']}/salesforce-credentials/test", cookies=c)
    assert r.status_code == 422


def test_salesforce_test_connection_succeeds(client, monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def test_connection(self):
            return {"ok": True, "versions": 5}

    monkeypatch.setattr("app.integrations.clients.SalesforceClient", _FakeClient)
    c = auth_cookies("sfco5", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/salesforce-credentials", cookies=c, json={
        "client_id": "cid", "client_secret": "secret", "instance_url": "https://acme.my.salesforce.com",
    })
    r = client.post(f"/api/v1/agents/{agent['id']}/salesforce-credentials/test", cookies=c)
    assert r.status_code == 200 and r.json() == {"ok": True, "versions": 5}


def test_salesforce_connections_require_editor_role(client):
    c = auth_cookies("sfco6", "viewer")
    assert client.post("/api/v1/agents/x/salesforce-credentials", cookies=c, json={
        "client_id": "a", "client_secret": "b", "instance_url": "https://x.salesforce.com",
    }).status_code == 403
    assert client.delete("/api/v1/agents/x/salesforce-credentials", cookies=c).status_code == 403
    assert client.post("/api/v1/agents/x/salesforce-credentials/test", cookies=c).status_code == 403
