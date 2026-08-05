"""QIK-518: real readiness and the system statistics dashboard.

/health returned a static dict, so a deploy could be declared successful against an unreachable
database, and nothing surfaced connection headroom, Redis eviction or queue depth.
"""
import asyncio

import pytest

from app.modules.health import system
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import AdminRole, Capability, default_capabilities
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "sys-admin.invalid"


def _admin(client) -> dict:
    bootstrap_admin(client, ADMIN)
    return auth_cookies("platform", "viewer", email=ADMIN)


def _grant(client, email: str, capabilities: list[str]) -> dict:
    cookies = _admin(client)
    token = csrf.generate_csrf_token()
    client.put(f"/api/v1/admin/org/{email}", cookies={**cookies, csrf.CSRF_COOKIE: token},
               headers={csrf.CSRF_HEADER: token},
               json={"role": "viewer", "capabilities": capabilities})
    return auth_cookies("platform", "viewer", email=email)


# --- liveness stays liveness ----------------------------------------------------------------------

def test_liveness_does_not_probe_dependencies(client):
    """A liveness probe that fails on a database blip makes Docker restart a healthy container,
    turning a short outage into a crash loop and a longer one."""
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert "checks" not in body


def test_readiness_reports_each_dependency(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    names = {check["name"] for check in response.json()["checks"]}
    assert names == {"database", "redis"}


def test_readiness_returns_503_when_a_dependency_is_down(client, monkeypatch):
    """This is the whole point: a deploy gate could previously not tell "the process is up" from
    "the process can serve"."""
    class Broken:
        def __call__(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(client.app.state, "sessionmaker", Broken(), raising=False)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    failed = next(c for c in response.json()["checks"] if c["name"] == "database")
    assert failed["ok"] is False


def test_a_probe_failure_never_leaks_a_connection_string(client, monkeypatch):
    """The endpoint is unauthenticated so a load balancer can use it, so the reason must be a class
    name and never a driver message."""
    secret = "postgresql://user:sup3rsecret@db.internal:5432/qiko"

    class Leaky:
        def __call__(self):
            raise RuntimeError(f"could not connect to {secret}")

    monkeypatch.setattr(client.app.state, "sessionmaker", Leaky(), raising=False)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "sup3rsecret" not in response.text and secret not in response.text
    assert "RuntimeError" in response.text


def test_a_hanging_dependency_is_not_ready_rather_than_a_hung_request():
    async def scenario():
        async def never() -> str:
            await asyncio.sleep(60)
            return "unreachable"

        monkey = system.PROBE_TIMEOUT_SECONDS
        try:
            system.PROBE_TIMEOUT_SECONDS = 0.05
            probe = await system._timed("slow", never())
        finally:
            system.PROBE_TIMEOUT_SECONDS = monkey
        return probe

    probe = asyncio.run(scenario())
    assert probe.ok is False and "timed out" in probe.detail


# --- the dashboard --------------------------------------------------------------------------------

def test_system_stats_reports_process_facts_without_psutil(client):
    body = client.get("/api/v1/admin/system", cookies=_admin(client)).json()
    process = body["process"]
    assert process["uptime_seconds"] >= 0
    assert process["max_rss_kb"] > 0 and process["cpu_count"] >= 1
    assert process["python"].startswith("3.")
    assert body["ready"] is True


def test_each_collector_degrades_instead_of_failing_the_dashboard(client):
    """On SQLite the Postgres catalogue views do not exist, and in dev Redis is not configured. A
    dashboard that 500s in those cases is one nobody trusts."""
    body = client.get("/api/v1/admin/system", cookies=_admin(client)).json()
    assert body["database"]["available"] is False and body["database"]["reason"]
    assert body["redis"]["available"] is False
    assert body["queue"]["available"] is False


def test_a_broken_collector_reports_a_class_name_not_a_driver_message(client, monkeypatch):
    async def explode(_sessionmaker):
        raise RuntimeError("password authentication failed for user qiko")

    monkeypatch.setattr("app.modules.admin.router.database_stats", explode)
    body = client.get("/api/v1/admin/system", cookies=_admin(client)).json()
    assert body["database"]["available"] is False
    assert "password" not in body["database"]["reason"]


def test_system_stats_needs_view_system_stats_specifically(client):
    reader = _grant(client, "cust.sys@invalid", [Capability.view_customers.value])
    assert client.get("/api/v1/admin/system", cookies=reader).status_code == 403

    sysadmin = _grant(client, "sys.only@invalid", [Capability.view_system_stats.value])
    assert client.get("/api/v1/admin/system", cookies=sysadmin).status_code == 200
    # and it gains nothing else
    assert client.get("/api/v1/admin/tenants", cookies=sysadmin).status_code == 403
    assert client.get("/api/v1/admin/ai-cost", cookies=sysadmin).status_code == 403


def test_system_stats_is_closed_to_outsiders(client):
    assert client.get("/api/v1/admin/system").status_code == 401
    assert client.get("/api/v1/admin/system", cookies=auth_cookies("acme", "owner")).status_code == 403


def test_a_super_admin_keeps_the_new_capability_by_default():
    assert Capability.view_system_stats in default_capabilities(AdminRole.super_admin)
    assert Capability.view_system_stats not in default_capabilities(AdminRole.viewer)


@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/health/ready"])
def test_health_endpoints_stay_unauthenticated(client, path):
    """A load balancer and the deploy gate have no credentials."""
    assert client.get(path).status_code in (200, 503)
