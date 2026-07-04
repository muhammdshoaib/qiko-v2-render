from tests.helpers import auth_cookies

A = auth_cookies("adm", "admin")


def test_customer_detail_404_when_empty(client):
    assert client.get("/api/v1/admin/customers/nope", cookies=A).status_code == 404
    assert client.post("/api/v1/admin/customers/nope/studio", json={"enabled": True}, cookies=A).status_code == 404
    assert client.delete("/api/v1/admin/customers/nope", cookies=A).status_code == 404


def test_customer_detail_requires_admin(client):
    assert client.get("/api/v1/admin/customers/x", cookies=auth_cookies("adm", "viewer")).status_code == 403
