"""The free-form config patch: the widest write in the tenant app.

One dict, merged into the config every other feature reads from. The security review found it bypassed
the entire credential audit built in wave 2: an editor could set any *_encrypted key through it with no
row, no encryption and no rotation fingerprint. Wave 2's own test counted encrypt() call sites against
audit calls, which this path does not trip.
"""
import asyncio

from app.modules.agents.service import Agent
from app.modules.audit import registry
from tests.helpers import auth_cookies

C = auth_cookies("cfgco", "owner", user_id="u-cfg", email="owner@cfgco.invalid")

SECRET = "xoxb-not-a-real-token"


def _worker(client, worker_id: str = "w1", config: dict | None = None) -> None:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=worker_id, tenant="cfgco", name="Bid Bot", config=config or {})))


def _rows(client, action: str = registry.WORKER_CONFIG_CHANGED) -> list[dict]:
    return [r for r in client.app.state.audit.rows if r["action"] == action]


def test_a_credential_key_is_refused_not_audited(client):
    """Refused rather than recorded, because auditing it would note that something happened while still
    letting a value bypass the encryption the field's name asserts. The dedicated endpoint encrypts the
    value, fingerprints the plaintext and writes its row inside the store's transaction; none of that
    happens here."""
    _worker(client)
    response = client.put("/api/v1/agents/w1/config", cookies=C,
                          json={"patch": {"slack_bot_token_encrypted": SECRET}})
    assert response.status_code == 422
    assert "dedicated endpoint" in response.json()["detail"]
    assert SECRET not in str(client.app.state.audit.rows)

    stored = asyncio.run(client.app.state.agents.get("cfgco", "w1"))
    assert "slack_bot_token_encrypted" not in stored.config, "and nothing was written"


def test_the_connection_flags_are_refused_too(client):
    """Flipping the flag without the secret produces a worker claiming a connection it does not have,
    which fails later at the third party with an error the customer cannot act on."""
    _worker(client)
    response = client.put("/api/v1/agents/w1/config", cookies=C,
                          json={"patch": {"slack_credentials_added": True}})
    assert response.status_code == 422


def test_every_redacted_read_key_is_also_refused_on_write(client):
    """The read list existed and was not applied symmetrically to writes, which is the whole defect."""
    from app.modules.agents.router import _REDACTED_CONFIG_KEYS

    _worker(client)
    for key in _REDACTED_CONFIG_KEYS:
        response = client.put("/api/v1/agents/w1/config", cookies=C, json={"patch": {key: "x"}})
        assert response.status_code == 422, f"{key} is readable-redacted but writable"


def test_a_legitimate_wizard_save_still_works(client):
    """The Train wizard's Background and Tone steps go through this endpoint. Refusing credential keys
    must not touch them."""
    _worker(client)
    response = client.put("/api/v1/agents/w1/config", cookies=C, json={"patch": {
        "expertise": "Tender writing", "tone": "formal", "main_goal": "win more bids"}})
    assert response.status_code == 200
    stored = asyncio.run(client.app.state.agents.get("cfgco", "w1"))
    assert stored.config["expertise"] == "Tender writing"


def test_a_scalar_setting_records_its_values(client):
    """"gate_threshold 0.7 to 0.4" is what an incident needs. Recording only that the threshold moved
    leaves the reader to go and ask."""
    _worker(client, config={"gate_threshold": 0.7})
    client.put("/api/v1/agents/w1/config", cookies=C, json={"patch": {"gate_threshold": 0.4}})

    row = _rows(client)[0]
    assert row["changes"]["gate_threshold"] == {"from": 0.7, "to": 0.4}
    assert row["actor_label"] == "owner@cfgco.invalid"
    assert row["target_id"] == "w1"


def test_free_text_is_named_but_never_copied(client):
    """Knowing the persona was rewritten is actionable. Copying it into a second store is the
    duplication the diff-not-snapshot rule exists to prevent, and it can contain customer names."""
    _worker(client, config={"system_prompt": "old prose"})
    client.put("/api/v1/agents/w1/config", cookies=C,
               json={"patch": {"system_prompt": "a long new prompt mentioning ACME Ltd"}})

    row = _rows(client)[0]
    assert "ACME Ltd" not in str(row), "the prose must not be in the row"
    assert "old prose" not in str(row), "nor the previous prose"
    assert row["event_metadata"]["rewritten_text_fields"] == ["system_prompt"]
    assert row["changes"] == {}, "no diff for prose"


def test_re_saving_an_unchanged_field_records_nothing_as_changed(client):
    """A wizard step re-saved without edits must not read as a threshold change. The snapshot comes
    from under the row lock, so "changed" means genuinely changed rather than merely submitted."""
    _worker(client, config={"tone": "formal", "gate_threshold": 0.5})
    client.put("/api/v1/agents/w1/config", cookies=C,
               json={"patch": {"tone": "formal", "gate_threshold": 0.5}})

    row = _rows(client)[0]
    assert row["event_metadata"]["changed_keys"] == []
    assert row["changes"] == {}
    # The submission is still recorded, because someone did act on the worker.
    assert set(row["event_metadata"]["submitted_keys"]) == {"tone", "gate_threshold"}


def test_a_patch_with_nothing_auditable_writes_no_row(client):
    """A row saying "the config changed, fields unknown" is noise that makes the real ones harder to
    find."""
    _worker(client)
    client.put("/api/v1/agents/w1/config", cookies=C, json={"patch": {"full_name": "Bid Bot Two"}})
    assert _rows(client) == []


def test_the_config_row_is_written_in_the_stores_transaction(client):
    """It uses the same callback the credential path does, so a config change cannot land unrecorded."""
    import inspect

    from app.modules.agents import router

    source = inspect.getsource(router.update_config)
    assert "audit=build_record if audited else None" in source
    assert "def build_record(previous: dict)" in source
