"""Functional API tests via TestClient: routers are authenticated, tenant-scoped (from token), RBAC-gated."""
from tests.helpers import auth_cookies

C = auth_cookies("acme", "owner")
ISO = "IDG holds a current ISO 9001 certification valid through 2027."


def test_unauthenticated_is_401(client):
    assert client.post("/api/v1/knowledge/search", json={"query": "x"}).status_code == 401


def test_tenant_comes_from_token_not_header(client):
    # even if a caller spoofs a header, the tenant is the token's; ingest under token tenant (acme)
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO},
                headers={"X-Tenant-Id": "attacker"}, cookies=C)
    hits = client.post("/api/v1/knowledge/search", json={"query": "ISO 9001"},
                       headers={"X-Tenant-Id": "attacker"}, cookies=C).json()["results"]
    assert any("ISO 9001" in h for h in hits)
    # a token for a different tenant sees nothing
    other = client.post("/api/v1/knowledge/search", json={"query": "ISO 9001"},
                        cookies=auth_cookies("beta")).json()["results"]
    assert other == []


def test_knowledge_ingest_list_delete(client):
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=C)
    assert client.get("/api/v1/knowledge/documents", cookies=C).json()[0]["doc_id"] == "iso"
    assert client.delete("/api/v1/knowledge/documents/iso", cookies=C).json()["removed"] >= 1


def test_agents_lifecycle_and_plan_gate(client):
    c = auth_cookies("agteam", "owner")
    created = client.post("/api/v1/agents", json={"name": "IDG", "plan": "free"}, cookies=c).json()
    assert created["status"] == "training"
    assert client.post(f"/api/v1/agents/{created['id']}/ready", cookies=c).json()["status"] == "ready"
    assert client.post("/api/v1/agents", json={"name": "second", "plan": "free"}, cookies=c).status_code == 403


def test_agents_write_requires_editor_role(client):
    # a viewer cannot create agents
    r = client.post("/api/v1/agents", json={"name": "x"}, cookies=auth_cookies("t", "viewer"))
    assert r.status_code == 403


def test_admin_requires_admin_role(client):
    subs = [{"customer_id": "c1", "plan": "pro", "price_cents": 5000}]
    assert client.post("/api/v1/admin/revenue", json=subs, cookies=auth_cookies("t", "editor")).status_code == 403
    ok = client.post("/api/v1/admin/revenue", json=subs, cookies=auth_cookies("t", "admin"))
    assert ok.json()["active_subscriptions"] == 1
