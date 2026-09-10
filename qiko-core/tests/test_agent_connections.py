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


# --- Per-worker Calendly + ClickUp connections (native V2 shape: tenant brings its own token) ---
def _agent(client, tenant: str):
    c = auth_cookies(tenant, "owner")
    return c, client.post("/api/v1/agents", json={"name": "W"}, cookies=c).json()["id"]


def test_calendly_credentials_save_mask_and_disconnect(client):
    c, aid = _agent(client, "calco")
    save = client.post(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c, json={"token": "cal-supersecret"})
    assert save.status_code == 200
    body = save.json()
    assert body["calendly_credentials_added"] is True
    assert "cal-supersecret" not in save.text and body["token_masked"]

    fetched = client.get(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c)
    assert fetched.status_code == 200 and fetched.json()["calendly_credentials_added"] is True
    assert "cal-supersecret" not in fetched.text
    # the ciphertext must not leak through the generic agent views either
    assert "calendly_token_encrypted" not in client.get("/api/v1/agents", cookies=c).text

    assert client.delete(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c).json()["disconnected"] is True
    assert client.get(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c).json()["calendly_credentials_added"] is False


def test_clickup_credentials_save_mask_and_disconnect(client):
    c, aid = _agent(client, "cuco")
    save = client.post(f"/api/v1/agents/{aid}/clickup-credentials", cookies=c,
                       json={"api_token": "pk-supersecret", "default_list_id": "L1"})
    assert save.status_code == 200
    body = save.json()
    assert body["clickup_credentials_added"] is True and body["default_list_id"] == "L1"
    assert "pk-supersecret" not in save.text and body["token_masked"]
    assert "clickup_api_token_encrypted" not in client.get("/api/v1/agents", cookies=c).text

    assert client.delete(f"/api/v1/agents/{aid}/clickup-credentials", cookies=c).json()["disconnected"] is True


def test_connection_tests_422_without_credentials(client):
    c, aid = _agent(client, "testco")
    assert client.post(f"/api/v1/agents/{aid}/calendly-credentials/test", cookies=c).status_code == 422
    assert client.post(f"/api/v1/agents/{aid}/clickup-credentials/test", cookies=c).status_code == 422


def test_calendly_and_clickup_tests_call_the_worker_token(client, monkeypatch):
    c, aid = _agent(client, "testco2")
    seen = {}

    class FakeCalendly:
        def __init__(self, token=None, client=None):
            seen["cal"] = token

        def test_connection(self):
            return {"ok": True, "user": "Acme"}

    class FakeClickUp:
        def __init__(self, api_token=None, client=None):
            seen["cu"] = api_token

        def test_connection(self):
            return {"ok": True, "user": "acme@invalid"}

    monkeypatch.setattr("app.integrations.clients.CalendlyClient", FakeCalendly)
    monkeypatch.setattr("app.integrations.clients.ClickUpClient", FakeClickUp)
    client.post(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c, json={"token": "cal-tok"})
    client.post(f"/api/v1/agents/{aid}/clickup-credentials", cookies=c, json={"api_token": "cu-tok"})
    assert client.post(f"/api/v1/agents/{aid}/calendly-credentials/test", cookies=c).json()["ok"] is True
    assert client.post(f"/api/v1/agents/{aid}/clickup-credentials/test", cookies=c).json()["ok"] is True
    assert seen == {"cal": "cal-tok", "cu": "cu-tok"}


def test_connection_writes_require_editor(client):
    owner = auth_cookies("roleco", "owner")
    aid = client.post("/api/v1/agents", json={"name": "W"}, cookies=owner).json()["id"]
    viewer = auth_cookies("roleco", "viewer")
    assert client.post(f"/api/v1/agents/{aid}/calendly-credentials", cookies=viewer,
                       json={"token": "t"}).status_code == 403
    assert client.post(f"/api/v1/agents/{aid}/clickup-credentials", cookies=viewer,
                       json={"api_token": "t"}).status_code == 403
    assert client.delete(f"/api/v1/agents/{aid}/calendly-credentials", cookies=viewer).status_code == 403


def test_tokens_are_ciphertext_at_rest_not_plaintext(client):
    """The masked view alone can't prove encryption (_mask hides the plaintext too), so assert the
    stored value directly: it must differ from the token and decrypt back to it."""
    import asyncio

    from app.core.crypto import decrypt

    c, aid = _agent(client, "atrest")
    client.post(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c, json={"token": "cal-plain"})
    client.post(f"/api/v1/agents/{aid}/clickup-credentials", cookies=c, json={"api_token": "cu-plain"})
    cfg = asyncio.run(client.app.state.agents.get("atrest", aid)).config
    assert cfg["calendly_token_encrypted"] != "cal-plain"
    assert cfg["clickup_api_token_encrypted"] != "cu-plain"
    assert decrypt(cfg["calendly_token_encrypted"]) == "cal-plain"
    assert decrypt(cfg["clickup_api_token_encrypted"]) == "cu-plain"


def test_another_tenant_cannot_read_or_write_these_credentials(client):
    c, aid = _agent(client, "tenantA")
    client.post(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c, json={"token": "secret-A"})
    other = auth_cookies("tenantB", "owner")
    for path in ("calendly-credentials", "clickup-credentials"):
        assert client.get(f"/api/v1/agents/{aid}/{path}", cookies=other).status_code == 404
        assert client.delete(f"/api/v1/agents/{aid}/{path}", cookies=other).status_code == 404
        assert client.post(f"/api/v1/agents/{aid}/{path}/test", cookies=other).status_code == 404
    assert client.post(f"/api/v1/agents/{aid}/calendly-credentials", cookies=other,
                       json={"token": "x"}).status_code == 404


def test_all_connection_writes_and_tests_require_editor(client):
    owner = auth_cookies("roleco2", "owner")
    aid = client.post("/api/v1/agents", json={"name": "W"}, cookies=owner).json()["id"]
    viewer = auth_cookies("roleco2", "viewer")
    assert client.delete(f"/api/v1/agents/{aid}/clickup-credentials", cookies=viewer).status_code == 403
    assert client.post(f"/api/v1/agents/{aid}/calendly-credentials/test", cookies=viewer).status_code == 403
    assert client.post(f"/api/v1/agents/{aid}/clickup-credentials/test", cookies=viewer).status_code == 403


def test_undecryptable_credential_asks_for_a_reconnect_instead_of_500(client):
    """After an encryption-key rotation the stored blob can't be read: fail closed with a 422."""
    import asyncio

    c, aid = _agent(client, "rotated")
    client.post(f"/api/v1/agents/{aid}/calendly-credentials", cookies=c, json={"token": "cal-plain"})
    asyncio.run(client.app.state.agents.update_config("rotated", aid, {"calendly_token_encrypted": "not-fernet"}))
    r = client.post(f"/api/v1/agents/{aid}/calendly-credentials/test", cookies=c)
    assert r.status_code == 422 and "reconnect" in r.json()["detail"]


# --- Per-worker Slack + Gmail connections -------------------------------------------------------
def test_slack_and_gmail_credentials_save_mask_and_disconnect(client):
    import asyncio

    from app.core.crypto import decrypt

    c, aid = _agent(client, "sgco")
    slack = client.post(f"/api/v1/agents/{aid}/slack-credentials", cookies=c,
                        json={"bot_token": "xoxb-supersecret", "default_channel": "#sales"})
    assert slack.status_code == 200
    assert slack.json()["slack_credentials_added"] is True
    assert slack.json()["default_channel"] == "#sales"
    assert "xoxb-supersecret" not in slack.text and slack.json()["token_masked"]

    gmail = client.post(f"/api/v1/agents/{aid}/gmail-credentials", cookies=c,
                        json={"address": "sales@acme.invalid", "app_password": "abcd efgh ijkl mnop"})
    assert gmail.status_code == 200
    assert gmail.json()["gmail_credentials_added"] is True
    assert gmail.json()["address"] == "sales@acme.invalid"
    assert "abcd efgh ijkl mnop" not in gmail.text and gmail.json()["app_password_masked"]

    # neither ciphertext may leak through the generic agent views
    listed = client.get("/api/v1/agents", cookies=c).text
    assert "slack_bot_token_encrypted" not in listed and "gmail_app_password_encrypted" not in listed

    # and both are genuinely encrypted at rest
    cfg = asyncio.run(client.app.state.agents.get("sgco", aid)).config
    assert cfg["slack_bot_token_encrypted"] != "xoxb-supersecret"
    assert decrypt(cfg["slack_bot_token_encrypted"]) == "xoxb-supersecret"
    assert decrypt(cfg["gmail_app_password_encrypted"]) == "abcd efgh ijkl mnop"

    for path in ("slack-credentials", "gmail-credentials"):
        assert client.delete(f"/api/v1/agents/{aid}/{path}", cookies=c).json()["disconnected"] is True


def test_gmail_credentials_reject_a_non_email_address(client):
    c, aid = _agent(client, "sgco2")
    r = client.post(f"/api/v1/agents/{aid}/gmail-credentials", cookies=c,
                    json={"address": "not-an-email", "app_password": "pw"})
    assert r.status_code == 422


def test_slack_and_gmail_are_tenant_isolated_and_editor_gated(client):
    c, aid = _agent(client, "sgtenantA")
    client.post(f"/api/v1/agents/{aid}/slack-credentials", cookies=c, json={"bot_token": "xoxb-A"})
    other = auth_cookies("sgtenantB", "owner")
    viewer = auth_cookies("sgtenantA", "viewer")
    for path in ("slack-credentials", "gmail-credentials"):
        assert client.get(f"/api/v1/agents/{aid}/{path}", cookies=other).status_code == 404
        assert client.delete(f"/api/v1/agents/{aid}/{path}", cookies=other).status_code == 404
        assert client.post(f"/api/v1/agents/{aid}/{path}/test", cookies=other).status_code == 404
        assert client.delete(f"/api/v1/agents/{aid}/{path}", cookies=viewer).status_code == 403
        assert client.post(f"/api/v1/agents/{aid}/{path}/test", cookies=viewer).status_code == 403


def test_slack_and_gmail_tests_422_without_credentials(client):
    c, aid = _agent(client, "sgco3")
    assert client.post(f"/api/v1/agents/{aid}/slack-credentials/test", cookies=c).status_code == 422


# --- Per-worker Interakt connection (JM2-1026) ---------------------------------------------------
def test_interakt_credentials_save_mask_and_disconnect(client):
    import asyncio

    from app.core.crypto import decrypt

    c, aid = _agent(client, "inco")
    save = client.post(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c,
                       json={"api_key": "ik-supersecret"})
    assert save.status_code == 200
    body = save.json()
    assert body["interakt_credentials_added"] is True
    assert "ik-supersecret" not in save.text
    assert body["api_key_masked"] and body["api_key_masked"] != "ik-supersecret"

    fetched = client.get(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c)
    assert fetched.status_code == 200 and fetched.json()["interakt_credentials_added"] is True
    assert "ik-supersecret" not in fetched.text

    # the ciphertext may not leak through the generic agent views
    listed = client.get("/api/v1/agents", cookies=c).text
    assert "interakt_api_key_encrypted" not in listed

    # and it is genuinely encrypted at rest, not stored as the plaintext it was sent as
    cfg = asyncio.run(client.app.state.agents.get("inco", aid)).config
    assert cfg["interakt_api_key_encrypted"] != "ik-supersecret"
    assert decrypt(cfg["interakt_api_key_encrypted"]) == "ik-supersecret"

    disconnected = client.delete(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c)
    assert disconnected.status_code == 200 and disconnected.json()["disconnected"] is True
    assert client.get(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c).json()["interakt_credentials_added"] is False


def test_interakt_credentials_are_tenant_isolated_and_editor_gated(client):
    c, aid = _agent(client, "intenantA")
    client.post(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c, json={"api_key": "ik-A"})
    other = auth_cookies("intenantB", "owner")
    viewer = auth_cookies("intenantA", "viewer")
    assert client.get(f"/api/v1/agents/{aid}/interakt-credentials", cookies=other).status_code == 404
    assert client.delete(f"/api/v1/agents/{aid}/interakt-credentials", cookies=other).status_code == 404
    assert client.post(f"/api/v1/agents/{aid}/interakt-credentials/test", cookies=other).status_code == 404
    assert client.post(f"/api/v1/agents/{aid}/interakt-credentials", cookies=other,
                       json={"api_key": "x"}).status_code == 404
    assert client.delete(f"/api/v1/agents/{aid}/interakt-credentials", cookies=viewer).status_code == 403
    assert client.post(f"/api/v1/agents/{aid}/interakt-credentials/test", cookies=viewer).status_code == 403


def test_interakt_test_connection_requires_credentials_first(client):
    c, aid = _agent(client, "inco2")
    r = client.post(f"/api/v1/agents/{aid}/interakt-credentials/test", cookies=c)
    assert r.status_code == 422


def test_interakt_test_connection_succeeds(client, monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def verify_credentials(self):
            return None

    monkeypatch.setattr("app.integrations.clients.InteraktClient", _FakeClient)
    c, aid = _agent(client, "inco3")
    client.post(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c, json={"api_key": "ik-good"})
    r = client.post(f"/api/v1/agents/{aid}/interakt-credentials/test", cookies=c)
    assert r.status_code == 200 and r.json() == {"verified": True}


def test_interakt_test_connection_surfaces_a_bad_key_as_502_not_500(client, monkeypatch):
    from app.integrations.clients import InteraktAuthError

    class _FailingClient:
        def __init__(self, **kwargs):
            pass

        def verify_credentials(self):
            raise InteraktAuthError("Interakt rejected this API key")

    monkeypatch.setattr("app.integrations.clients.InteraktClient", _FailingClient)
    c, aid = _agent(client, "inco4")
    client.post(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c, json={"api_key": "ik-bad"})
    r = client.post(f"/api/v1/agents/{aid}/interakt-credentials/test", cookies=c)
    assert r.status_code == 502


def test_interakt_undecryptable_credential_asks_for_a_reconnect_instead_of_500(client):
    import asyncio

    c, aid = _agent(client, "inco5")
    client.post(f"/api/v1/agents/{aid}/interakt-credentials", cookies=c, json={"api_key": "ik-x"})
    asyncio.run(client.app.state.agents.update_config(
        "inco5", aid, {"interakt_api_key_encrypted": "not-fernet"}))
    r = client.post(f"/api/v1/agents/{aid}/interakt-credentials/test", cookies=c)
    assert r.status_code == 422 and "reconnect" in r.json()["detail"]
