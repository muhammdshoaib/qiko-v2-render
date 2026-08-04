"""Guard the production wiring path.

`create_app()` installs in-memory defaults and the lifespan swaps them for Sql* stores only when
`use_db_stores` is true. Nothing exercised that branch before, and `app/main.py` was excluded from
coverage, which is exactly how four in-memory stores survived into production (generated files,
Slack installations, Slack workspace links, channel sessions). These tests fail if a NEW store is
added without a durable production implementation.
"""
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

# Stores that must be durable in production. Anything added to app.state that holds customer or
# tenant state belongs here.
DURABLE_STORES = (
    "knowledge", "chat", "crm", "agents", "rfp_packs", "requirements", "pack_answers",
    "pack_tree", "assignments", "notifications", "sales_intel", "sales_intel_ingest_filters",
    "salesforce_auth", "finance", "teams", "leads", "teams_notifier", "subscriptions",
    "admin_org", "otp_store", "pending_invites", "pending_signups", "consent", "customers",
    "payment_links",
)

# Known, deliberate exceptions with a recorded reason. Shrinking this list is the goal.
KNOWN_IN_MEMORY = {
    "file_generator": "generated documents are lost on restart and grow unbounded (S3Storage exists but is unwired)",
    "slack_oauth": "OAuth-installed Slack workspaces are lost on restart",
    "slack_links": "Slack user -> worker links are lost on restart",
    "channel_sessions": "per-channel sessions are lost on restart (no production consumer today)",
}


def _inner(store):
    """Services wrap their store; look one level in so we classify the real implementation."""
    return getattr(store, "store", store)


def test_production_wiring_replaces_durable_stores_with_sql(monkeypatch):
    monkeypatch.setattr(get_settings(), "use_db_stores", True)
    monkeypatch.setattr(get_settings(), "database_url", "sqlite+aiosqlite:///:memory:")
    with TestClient(create_app()) as client:
        assert client.app.state.sessionmaker is not None
        offenders = []
        for name in DURABLE_STORES:
            store = getattr(client.app.state, name, None)
            assert store is not None, f"app.state.{name} is missing"
            impl = type(_inner(store)).__name__
            if "InMemory" in impl:
                offenders.append(f"{name} -> {impl}")
        assert not offenders, (
            "these stores stay in-memory under production config, so they lose all data on every "
            f"restart/redeploy: {offenders}")


def test_known_in_memory_stores_are_declared_not_accidental(monkeypatch):
    """The four known offenders must stay declared here. If one is fixed, remove it from the dict;
    if a new one appears, this test forces a decision instead of letting it slip through."""
    monkeypatch.setattr(get_settings(), "use_db_stores", True)
    monkeypatch.setattr(get_settings(), "database_url", "sqlite+aiosqlite:///:memory:")
    with TestClient(create_app()) as client:
        for name, reason in KNOWN_IN_MEMORY.items():
            store = getattr(client.app.state, name, None)
            assert store is not None, f"app.state.{name} disappeared; update KNOWN_IN_MEMORY"
            assert reason, "every known offender needs a recorded reason"
