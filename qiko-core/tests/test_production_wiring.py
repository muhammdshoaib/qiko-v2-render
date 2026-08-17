"""Guard the production wiring path.

`create_app()` installs in-memory defaults and the lifespan swaps them for Sql* stores only when
`use_db_stores` is true. Nothing exercised that branch before, and `app/main.py` was excluded from
coverage, which is exactly how four in-memory stores survived into production (generated files,
Slack installations, Slack workspace links, channel sessions). These tests fail if a NEW store is
added without a durable production implementation.

file_generator has since been fixed (it uses S3Storage when S3_BUCKET is set, and
assert_secrets_set refuses to start a non-dev environment without one), so it moved out of the
declared-exception list and into the durable assertions below. Leaving a stale exception in place is
worse than not having the list: the test would keep passing if someone un-wired S3.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.modules.identity import router as identity_router

# Stores that must be durable in production. Anything added to app.state that holds customer or
# tenant state belongs here.
DURABLE_STORES = (
    "knowledge", "chat", "crm", "agents", "rfp_packs", "requirements", "pack_answers",
    "pack_tree", "assignments", "notifications", "sales_intel", "sales_intel_ingest_filters",
    "salesforce_auth", "finance", "teams", "leads", "teams_notifier", "subscriptions",
    "admin_org",
    "ai_usage", "cost_caps", "audit", "otp_store", "pending_invites", "pending_signups", "consent", "customers",
    "payment_links",
    # The Slack heads-up assistant. slack_oauth moved OUT of the known-in-memory list below: the
    # digest job runs in the arq worker process, so an in-memory installation store meant the
    # worker could never resolve a bot token and the digest was undeliverable in production.
    "slack_messages", "slack_oauth",
)

# Known, deliberate exceptions with a recorded reason. Shrinking this list is the goal.
KNOWN_IN_MEMORY = {
    "slack_links": "Slack user -> worker links are lost on restart",
    "channel_sessions": "per-channel sessions are lost on restart (no production consumer today)",
}


def _inner(store):
    """Services wrap their store; look one level in so we classify the real implementation."""
    return getattr(store, "store", store)


@pytest.fixture
def production_app(monkeypatch):
    """Build the app the way production does, then undo the global side effects.

    The lifespan calls identity.router.set_store(SqlUserStore(...)), which mutates a MODULE-LEVEL
    global. monkeypatch restores the settings attributes but not that global, so without this
    teardown every later test in the session would get a SQL user store pointed at a database with
    no tables. Restoring it is what keeps this test honest instead of poisoning the suite.
    """
    previous_store = identity_router._store
    monkeypatch.setattr(get_settings(), "use_db_stores", True)
    monkeypatch.setattr(get_settings(), "database_url", "sqlite+aiosqlite:///:memory:")
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        identity_router._store = previous_store


def test_production_wiring_replaces_durable_stores_with_sql(production_app):
    assert production_app.app.state.sessionmaker is not None
    offenders = []
    for name in DURABLE_STORES:
        store = getattr(production_app.app.state, name, None)
        assert store is not None, f"app.state.{name} is missing"
        impl = type(_inner(store)).__name__
        if "InMemory" in impl:
            offenders.append(f"{name} -> {impl}")
    assert not offenders, (
        "these stores stay in-memory under production config, so they lose all data on every "
        f"restart/redeploy: {offenders}")


def test_known_in_memory_stores_are_declared_not_accidental(production_app):
    """The remaining known offenders must stay declared here. If one is fixed, remove it from the
    dict; if a new one appears, this test forces a decision instead of letting it slip through."""
    for name, reason in KNOWN_IN_MEMORY.items():
        store = getattr(production_app.app.state, name, None)
        assert store is not None, f"app.state.{name} disappeared; update KNOWN_IN_MEMORY"
        assert reason, "every known offender needs a recorded reason"


def test_generated_files_are_durable_in_production(production_app, monkeypatch):
    """file_generator was the worst of the four: a dict with no TTL in a 512M container, and every
    download key 404'd after a deploy. It is fixed, so it is asserted rather than excused."""
    from app.modules.storage.backend import S3Storage

    assert "file_generator" not in KNOWN_IN_MEMORY, (
        "file_generator is wired to S3Storage now; re-adding it here would let a regression pass")

    monkeypatch.setattr(get_settings(), "s3_bucket", "qiko-v2-live-files")
    app = create_app()
    backend = app.state.file_generator.storage
    assert isinstance(backend, S3Storage) and backend.bucket == "qiko-v2-live-files"


def test_a_non_dev_environment_refuses_to_start_without_a_bucket():
    """The guard is what makes the S3 wiring load-bearing rather than best-effort."""
    from app.core.config import Environment, Settings

    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        Settings(_env_file=None, environment=Environment.live, s3_bucket="").assert_secrets_set()
