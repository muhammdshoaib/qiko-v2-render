def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "qiko-core"
    assert body["environment"] == "dev"


def test_health_api_v1_is_tenant_scoped(client):
    r = client.get("/api/v1/health", headers={"X-Tenant-Id": "acme"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
