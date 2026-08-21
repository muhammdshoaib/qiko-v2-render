from tests.helpers import auth_cookies, bootstrap_admin

ADMIN_EMAIL = "platform-admin4@qiko.ai"
_CSRF_COOKIE = {"qiko_csrf": "csrf-test"}
_CSRF_HEADERS = {"x-csrf-token": "csrf-test", "origin": "http://testserver"}


def _admin_cookies(client):
    bootstrap_admin(client, ADMIN_EMAIL)
    return {**auth_cookies("adm", "viewer", email=ADMIN_EMAIL), **_CSRF_COOKIE}


def test_customer_detail_404_when_empty(client):
    a = _admin_cookies(client)
    assert client.get("/api/v1/admin/customers/nope", cookies=a).status_code == 404
    assert client.post(
        "/api/v1/admin/customers/nope/studio",
        json={"enabled": True},
        cookies=a,
        headers=_CSRF_HEADERS,
    ).status_code == 404
    assert client.delete(
        "/api/v1/admin/customers/nope", cookies=a, headers=_CSRF_HEADERS
    ).status_code == 404


def test_customer_detail_requires_admin(client):
    # neither a plain tenant viewer nor a tenant "admin" is a platform admin
    assert client.get("/api/v1/admin/customers/x", cookies=auth_cookies("adm", "viewer")).status_code == 403
    assert client.get("/api/v1/admin/customers/x", cookies=auth_cookies("adm", "admin")).status_code == 403
