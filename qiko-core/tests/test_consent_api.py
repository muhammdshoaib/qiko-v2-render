from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app
from app.modules.consent import service as consent_service
from app.modules.consent.models import (
    COOKIES_RELEASE_ID,
    PRIVACY_RELEASE_ID,
    TERMS_RELEASE_ID,
    ConsentChoices,
)
from app.modules.consent.service import ConsentService
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.security import hash_password
from app.modules.identity.store import InMemoryUserStore, User


def _decision(decision_id: str, client_revision: int, *, preferences: bool,
              analytics: bool, marketing: bool) -> dict:
    return {
        "decision_id": decision_id, "client_revision": client_revision,
        "terms_release_id": TERMS_RELEASE_ID, "privacy_release_id": PRIVACY_RELEASE_ID,
        "cookies_release_id": COOKIES_RELEASE_ID, "preferences": preferences,
        "analytics": analytics, "marketing": marketing,
    }


def test_non_dev_requires_consent_pseudonym_keyring():
    settings = Settings(environment=Environment.preprod, session_secret="sec" + "ure-session-key",
                        use_db_stores=True, task_backend="arq")
    with pytest.raises(RuntimeError, match="CONSENT_PSEUDONYM_KEYS"):
        settings.assert_secrets_set()


def test_consent_pseudonym_survives_session_secret_rotation(monkeypatch):
    monkeypatch.setattr(consent_service, "get_settings", lambda: SimpleNamespace(
        encryption_key="stable" + "-consent-root", session_secret="sess" + "ion-one"))
    first = consent_service.pseudonymous_subject("user", "user-1")
    monkeypatch.setattr(consent_service, "get_settings", lambda: SimpleNamespace(
        encryption_key="stable" + "-consent-root", session_secret="sess" + "ion-two"))
    assert consent_service.pseudonymous_subject("user", "user-1") == first


async def test_consent_keyring_reads_legacy_history_after_rotation(monkeypatch):
    service = ConsentService()
    monkeypatch.setattr(consent_service, "get_settings", lambda: SimpleNamespace(
        consent_pseudonym_keys={"v1": "a" * 32}, consent_pseudonym_active_version="v1"))
    first = await service.record(
        namespace="user", identifier="user-1", choices=ConsentChoices(False, False, False),
        source="authenticated", decision_id="legacy-decision")
    monkeypatch.setattr(consent_service, "get_settings", lambda: SimpleNamespace(
        consent_pseudonym_keys={"v1": "a" * 32, "v2": "b" * 32},
        consent_pseudonym_active_version="v2"))
    assert (await service.latest(namespace="user", identifier="user-1")).id == first.id
    retry = await service.record(
        namespace="user", identifier="user-1", choices=ConsentChoices(False, False, False),
        source="authenticated", decision_id="legacy-decision",
        client_revision=first.client_revision)
    assert retry.id == first.id
    second = await service.record(
        namespace="user", identifier="user-1", choices=ConsentChoices(True, False, False),
        source="authenticated", decision_id="rotated-decision")
    assert second.key_version == "v2" and second.revision == first.revision + 1


def test_anonymous_consent_is_append_only_and_server_derives_audit_fields():
    app = create_app()
    client = TestClient(app)
    anonymous_id = "browser-generated-id-12345"

    rejected = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id, **_decision(
        "decision-reject", 1_000, preferences=False, analytics=False, marketing=False)})
    assert rejected.status_code == 201
    assert rejected.json()["source"] == "anonymous"
    assert rejected.json()["action"] == "reject"

    accepted = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id, **_decision(
        "decision-accept", 2_000, preferences=True, analytics=True, marketing=False)})
    assert accepted.status_code == 201 and accepted.json()["action"] == "update"
    withdrawn = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id, **_decision(
        "decision-withdraw", 3_000, preferences=False, analytics=False, marketing=False)})
    assert withdrawn.status_code == 201 and withdrawn.json()["action"] == "withdraw"
    assert len(app.state.consent.store.records) == 3
    duplicate = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id, **_decision(
        "decision-withdraw", 3_000, preferences=False, analytics=False, marketing=False)})
    assert duplicate.status_code == 201 and len(app.state.consent.store.records) == 3
    mismatched = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id, **_decision(
        "decision-withdraw", 3_000, preferences=True, analytics=True, marketing=True)})
    assert mismatched.status_code == 409
    cross_subject = client.post("/api/v1/consent/anonymous", json={"anonymous_id": "another-browser-id-12345", **_decision(
        "decision-withdraw", 3_000, preferences=False, analytics=False, marketing=False)})
    assert cross_subject.status_code == 409
    assert len(app.state.consent.store.records) == 3
    assert all(record.subject_hmac != anonymous_id for record in app.state.consent.store.records)
    assert client.get(
        "/api/v1/consent/anonymous", params={"anonymous_id": anonymous_id}
    ).json()["id"] == withdrawn.json()["id"]


def test_consent_api_rejects_delayed_older_cross_tab_decision():
    client = TestClient(create_app())
    anonymous_id = "cross-tab-browser-id-12345"
    latest = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id,
        **_decision("later-withdrawal", 2_000, preferences=False, analytics=False, marketing=False)})
    delayed = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id,
        **_decision("older-acceptance", 1_000, preferences=True, analytics=True, marketing=True)})
    assert latest.status_code == 201 and delayed.status_code == 409
    assert client.get("/api/v1/consent/anonymous", params={"anonymous_id": anonymous_id}).json()["id"] == latest.json()["id"]


def test_equal_cross_tab_revision_prefers_withdrawal():
    client = TestClient(create_app())
    anonymous_id = "equal-revision-browser-12345"
    accepted = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id,
        **_decision("equal-accept", 4_000, preferences=True, analytics=True, marketing=True)})
    withdrawn = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id,
        **_decision("equal-withdraw", 4_000, preferences=False, analytics=False, marketing=False)})
    assert accepted.status_code == 201 and withdrawn.status_code == 201
    assert withdrawn.json()["action"] == "withdraw"


def test_equal_revision_preserves_partial_withdrawal():
    client = TestClient(create_app())
    anonymous_id = "partial-withdraw-browser-12345"
    accepted = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id,
        **_decision("partial-accept", 5_000, preferences=True, analytics=True, marketing=True)})
    partial = client.post("/api/v1/consent/anonymous", json={"anonymous_id": anonymous_id,
        **_decision("partial-withdraw", 5_000, preferences=True, analytics=True, marketing=False)})
    assert accepted.status_code == 201 and partial.status_code == 201
    assert partial.json()["preferences"] is True and partial.json()["analytics"] is True
    assert partial.json()["marketing"] is False


def test_consent_api_rejects_stale_policy_release():
    client = TestClient(create_app())
    body = _decision("stale-policy", 1_000, preferences=True, analytics=False, marketing=False)
    body["terms_release_id"] = "terms-older"
    response = client.post("/api/v1/consent/anonymous", json={
        "anonymous_id": "stale-policy-browser-12345", **body})
    assert response.status_code == 422


def test_consent_api_rejects_client_supplied_source_and_action():
    client = TestClient(create_app())
    response = client.post("/api/v1/consent/anonymous", json={"anonymous_id": "browser-generated-id-12345", **_decision(
        "decision-forbidden", 1_000, preferences=True, analytics=True, marketing=True),
        "source": "signup", "action": "accept"})
    assert response.status_code == 422


def test_authenticated_consent_uses_verified_user_and_requires_csrf():
    app = create_app()
    store = InMemoryUserStore()
    store.seed(User(
        id="consent-user",
        email="consent" + "@" + "example.test",
        password_hash=hash_password("pw12345678"),
        tenant="acme",
        role=Role.owner,
    ))
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    assert client.post("/api/v1/auth/login", json={
        "email": "consent" + "@" + "example.test", "password": "pw12345678"
    }).status_code == 200

    body = _decision("authenticated-decision", 1_000,
                     preferences=True, analytics=False, marketing=False)
    assert client.post("/api/v1/consent", json=body).status_code == 403
    csrf = client.cookies["qiko_csrf"]
    response = client.post("/api/v1/consent", json=body, headers={"x-csrf-token": csrf})
    assert response.status_code == 201
    assert response.json()["source"] == "authenticated"
    assert response.json()["action"] == "accept"
    assert client.get("/api/v1/consent").json()["id"] == response.json()["id"]
    stored = app.state.consent.store.records[0]
    assert stored.subject_hmac != "consent-user"
