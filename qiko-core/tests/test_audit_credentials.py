"""Wave 2 of audit coverage: credentials.

Seventeen endpoints write, destroy or exercise an encrypted integration secret and not one of them
recorded anything. A customer's Salesforce client secret could be replaced and the only evidence was
that the ciphertext in the config column had changed, with no actor and no timestamp of its own.
"""
import pytest

from app.modules.agents.service import Agent
from app.modules.audit import registry
from app.modules.audit.credentials import PROVIDERS
from tests.helpers import auth_cookies

C = auth_cookies("credco", "owner")

SECRET = "sk_live_notarealsecret_9f2c"


def _worker(client, worker_id: str = "w1") -> None:
    import asyncio

    asyncio.run(client.app.state.agents.store.add(
        Agent(id=worker_id, tenant="credco", name="Tender Bot")))


def _events(client) -> list[dict]:
    return client.app.state.audit.rows


def test_setting_a_credential_is_recorded_without_the_credential(client):
    _worker(client)
    response = client.post("/api/v1/agents/w1/slack-credentials", cookies=C,
                           json={"bot_token": SECRET})
    assert response.status_code == 200

    rows = [r for r in _events(client) if r["action"] == registry.CREDENTIAL_SET]
    assert len(rows) == 1
    row = rows[0]
    assert row["changes"]["provider"] == "slack"
    assert row["changes"]["key"] == "slack_bot_token_encrypted"
    assert row["target_id"] == "w1" and row["tenant_id"] == "credco"
    # The whole point: the value is nowhere in the row, in any form.
    assert SECRET not in str(row)


def test_the_fingerprint_distinguishes_a_rotation_from_a_re_save(client, monkeypatch):
    """A bare "the token changed" cannot answer the question an incident raises, which is whether the
    leaked value is dead or still live."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "encryption_key", "Enc-Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4")
    _worker(client)

    client.post("/api/v1/agents/w1/slack-credentials", cookies=C, json={"bot_token": "first-value"})
    client.post("/api/v1/agents/w1/slack-credentials", cookies=C, json={"bot_token": "first-value"})
    client.post("/api/v1/agents/w1/slack-credentials", cookies=C, json={"bot_token": "second-value"})

    rows = [r for r in _events(client) if r["action"] == registry.CREDENTIAL_SET]
    assert len(rows) == 3
    assert rows[0]["event_metadata"]["rotated"] is True, "first write is a rotation from nothing"
    assert rows[1]["event_metadata"]["rotated"] is False, "re-saving the same value is not a rotation"
    assert rows[2]["event_metadata"]["rotated"] is True
    # The fingerprint follows the value, not the ciphertext: two encryptions of one value differ, so a
    # ciphertext fingerprint would have called the second write a rotation.
    assert rows[0]["event_metadata"]["fingerprint_after"] == rows[1]["event_metadata"]["fingerprint_after"]
    assert rows[2]["event_metadata"]["fingerprint_after"] != rows[1]["event_metadata"]["fingerprint_after"]


def test_disconnecting_is_its_own_event(client):
    """A disconnect silently stops an integration working, and the customer's next question is why
    their Slack notifications stopped. That is a different event from a rotation."""
    _worker(client)
    client.post("/api/v1/agents/w1/slack-credentials", cookies=C, json={"bot_token": SECRET})
    response = client.delete("/api/v1/agents/w1/slack-credentials", cookies=C)
    assert response.status_code == 200

    removed = [r for r in _events(client) if r["action"] == registry.CREDENTIAL_REMOVED]
    assert len(removed) == 1 and removed[0]["changes"]["provider"] == "slack"
    assert SECRET not in str(removed[0])


@pytest.mark.parametrize("provider,path,payload", [
    ("vapi", "vapi-credentials", {"vapi_api_key": SECRET, "vapi_public_key": "pk", "vapi_assistant_id": "a"}),
    ("salesforce", "salesforce-credentials",
     {"client_id": "cid", "client_secret": SECRET, "instance_url": "https://x.my.salesforce.com"}),
    ("calendly", "calendly-credentials", {"token": SECRET}),
    ("clickup", "clickup-credentials", {"api_token": SECRET}),
    ("slack", "slack-credentials", {"bot_token": SECRET}),
    ("gmail", "gmail-credentials", {"address": "a@b.invalid", "app_password": SECRET}),
])
def test_no_provider_leaks_its_secret(client, provider, path, payload):
    """Parametrised over every provider, because the discipline that matters here is exactly the kind
    that gets forgotten at the sixth copy."""
    _worker(client)
    client.post(f"/api/v1/agents/w1/{path}", cookies=C, json=payload)

    rows = [r for r in _events(client) if r["action"] == registry.CREDENTIAL_SET]
    assert rows and rows[-1]["changes"]["provider"] == provider
    assert SECRET not in str(rows[-1])


def test_every_declared_provider_key_matches_a_real_config_key():
    """The provider table is what stops a new integration being added with its secret quietly outside
    the audited set."""
    from pathlib import Path

    router = (Path(__file__).resolve().parents[1] / "app" / "modules" / "agents" / "router.py").read_text()
    for provider, key in PROVIDERS.items():
        if provider == "teams":
            continue  # lives in the channels router
        assert key in router, f"{provider} declares {key}, which the router never writes"


def test_the_router_writes_no_credential_without_auditing_it():
    """Counted from the source: a seventh integration added later cannot silently skip the audit."""
    from pathlib import Path

    router = (Path(__file__).resolve().parents[1] / "app" / "modules" / "agents" / "router.py").read_text()
    encrypt_writes = router.count("_encrypted\": encrypt(")
    audited = router.count("CREDENTIAL_SET")
    assert encrypt_writes == audited, (
        f"{encrypt_writes} credential writes but {audited} audit calls")


def test_the_credential_row_is_written_in_the_same_transaction(client):
    """The gate found that record_in had zero call sites, so every CRITICAL event was on the path
    that is allowed to lose the row. This is the first real one.

    A credential rotation that lands with no record of who performed it is the worst case for this
    table: the config visibly changed and nobody can say who changed it.
    """
    import inspect

    from app.db.stores import SqlAgentStore

    source = inspect.getsource(SqlAgentStore.update_config)
    # One transaction, the row added inside it, and the lock taken before the snapshot is read.
    assert "async with self.sessionmaker() as s, s.begin():" in source
    assert "with_for_update()" in source
    assert source.index("with_for_update()") < source.index("previous = dict(")
    assert "s.add(AuditEventRow(**audit(previous)))" in source
    assert source.index("row.config = {**previous") < source.index("s.add(AuditEventRow")


def test_no_credential_write_logs_the_wrong_path_warning(client, caplog):
    """record() shouts when a CRITICAL action arrives on the non-transactional path. That warning
    fired on every credential write until this leg, which is exactly what it is for."""
    import logging

    _worker(client)
    with caplog.at_level(logging.ERROR):
        client.post("/api/v1/agents/w1/slack-credentials", cookies=C, json={"bot_token": SECRET})
    assert "non-transactional path" not in caplog.text


def test_the_snapshot_cannot_be_a_live_reference(client, monkeypatch):
    """The in-memory store hands back live objects. An earlier version read the agent before the
    update and passed its config in, so the update mutated the very dict the audit was about to
    compare against, and every row reported that nothing had changed."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "encryption_key", "Enc-Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4")
    _worker(client)
    client.post("/api/v1/agents/w1/slack-credentials", cookies=C, json={"bot_token": "one"})
    client.post("/api/v1/agents/w1/slack-credentials", cookies=C, json={"bot_token": "two"})

    rows = [r for r in _events(client) if r["action"] == registry.CREDENTIAL_SET]
    before, after = rows[1]["event_metadata"]["fingerprint_before"], rows[1]["event_metadata"]["fingerprint_after"]
    assert before != after, "the second write must see the first value, not its own"
