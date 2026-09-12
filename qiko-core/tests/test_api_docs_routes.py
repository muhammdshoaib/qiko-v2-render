"""The two documentation routes (JM2-1134).

The spec endpoint is authenticated exactly like the rest of the worker API. The shell is
not, deliberately: a browser cannot attach X-Api-Key to a navigation, so the page is a
container that holds no contract content until the caller supplies a key to it.
"""
from app.core.config import get_settings

PREPROD_SERVER = {"url": "https://preprod.qiko.ai/api/v1", "description": "Preprod"}


def _worker_headers(monkeypatch, api_key: str = "test-key") -> dict:
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", api_key)
    return {"X-Api-Key": api_key, "X-Tenant-Id": "joseph-mews"}


def test_spec_reveals_nothing_to_an_unauthenticated_caller(client, monkeypatch):
    """No headers at all gets 404, not 403: require_worker_caller resolves the tenant before
    it looks at the key, so an anonymous caller cannot even confirm the tenant exists. That
    is the existing contract for this whole worker surface and documentation follows it."""
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", "test-key")
    response = client.get("/api/v1/tenants/joseph-mews/openapi.json")
    assert response.status_code == 404


def test_spec_requires_a_key_once_the_tenant_is_named(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", "test-key")
    response = client.get(
        "/api/v1/tenants/joseph-mews/openapi.json", headers={"X-Tenant-Id": "joseph-mews"})
    assert response.status_code == 403


def test_spec_rejects_a_wrong_key(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", "test-key")
    response = client.get(
        "/api/v1/tenants/joseph-mews/openapi.json",
        headers={"X-Api-Key": "not-the-key", "X-Tenant-Id": "joseph-mews"},
    )
    assert response.status_code == 403


def test_spec_returns_the_filtered_document(client, monkeypatch):
    response = client.get(
        "/api/v1/tenants/joseph-mews/openapi.json", headers=_worker_headers(monkeypatch))
    assert response.status_code == 200
    body = response.json()
    assert body["info"]["title"] == "Joseph Mews Worker API"
    assert body["servers"] == [PREPROD_SERVER]
    assert body["paths"], "expected the worker paths"
    for operations in body["paths"].values():
        for operation in operations.values():
            assert "joseph-mews-worker" in operation["tags"]


def test_spec_does_not_document_itself(client, monkeypatch):
    """The documentation routes carry their own tag, so they must not appear inside a
    tenant's contract."""
    body = client.get(
        "/api/v1/tenants/joseph-mews/openapi.json",
        headers=_worker_headers(monkeypatch)).json()
    assert not [p for p in body["paths"] if p.endswith("/docs")]
    assert not [p for p in body["paths"] if p.endswith("/openapi.json")]


def test_spec_rejects_an_unknown_tenant(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", "test-key")
    response = client.get(
        "/api/v1/tenants/someone-else/openapi.json",
        headers={"X-Api-Key": "test-key", "X-Tenant-Id": "someone-else"},
    )
    assert response.status_code == 404


def test_shell_is_served_without_a_key(client):
    response = client.get("/api/v1/tenants/joseph-mews/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_shell_carries_no_contract_content(client):
    """Without a key the page must reveal nothing about the API surface."""
    body = client.get("/api/v1/tenants/joseph-mews/docs").text
    assert "/insights/portfolio" not in body
    assert "/activity/intent-signals" not in body
    assert "joseph-mews-worker" not in body


def test_shell_never_persists_the_key(client):
    """The key is a shared service-to-service credential and the platform CSP permits
    inline script, so anything that could read it back without the holder present is a
    liability. It lives in a closure for the life of the page and nowhere else."""
    served = client.get("/api/v1/tenants/joseph-mews/docs").text
    served += client.get("/api/v1/docs-assets/docs-shell.js").text
    # Usage, not vocabulary: the script explains in a comment why it does not persist the
    # key, and that explanation is worth keeping.
    for call in ("sessionStorage.setItem", "sessionStorage.getItem",
                 "localStorage.setItem", "localStorage.getItem",
                 "document.cookie"):
        assert call not in served, call


def test_shell_behaviour_is_not_inline(client):
    """The application's own SecurityHeadersMiddleware sends default-src 'self' with no
    script-src, and Caddyfile.dev sets no CSP at all, so an inline script is blocked in
    local development while working on preprod only because Caddy replaces the header.
    Loading from a file satisfies 'self' under every policy."""
    body = client.get("/api/v1/tenants/joseph-mews/docs").text
    assert "/api/v1/docs-assets/docs-shell.js" in body
    assert "addEventListener" not in body
    assert "SwaggerUIBundle(" not in body


def test_the_two_tenant_allowlists_agree(client):
    """Authorisation depends on two lists: TENANT_SPECS here, and the tenant the worker
    dependency accepts. They are fail-closed today, but nothing bound them together, and if
    the dependency were widened for a second tenant while still resolving the joseph-mews
    agent's key, that key would authorise another tenant's contract."""
    from app.modules.api_docs.spec_filter import TENANT_SPECS
    from app.modules.joseph_mews.router import _KNOWN_TENANT

    assert set(TENANT_SPECS) == {_KNOWN_TENANT}


def test_vendor_notes_are_not_publicly_served(client):
    """The pin file names the exact renderer version. It sits outside the mount so an
    anonymous caller cannot read it off the server."""
    assert client.get("/api/v1/docs-assets/VENDOR.md").status_code == 404


def test_shell_ships_no_key_of_its_own(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", "a-real-looking-secret")
    body = client.get("/api/v1/tenants/joseph-mews/docs").text
    assert "a-real-looking-secret" not in body


def test_shell_references_only_same_origin_assets(client):
    """CSP allows scripts from 'self' only, so a CDN reference would silently fail to
    execute and the page would render blank."""
    body = client.get("/api/v1/tenants/joseph-mews/docs").text
    assert "/api/v1/docs-assets/swagger-ui-bundle.js" in body
    assert "/api/v1/docs-assets/swagger-ui.css" in body
    assert "unpkg.com" not in body
    assert "cdn.jsdelivr.net" not in body


def test_shell_offers_preprod_and_shows_live_as_coming_soon(client):
    body = client.get("/api/v1/tenants/joseph-mews/docs").text
    assert "https://preprod.qiko.ai/api/v1" in body
    assert "coming soon" in body.lower()
    assert "disabled" in body


def test_shell_rejects_an_unknown_tenant(client):
    assert client.get("/api/v1/tenants/someone-else/docs").status_code == 404


def test_assets_are_served(client):
    for asset in ("swagger-ui.css", "swagger-ui-bundle.js"):
        response = client.get(f"/api/v1/docs-assets/{asset}")
        assert response.status_code == 200, asset
        assert response.content, asset


def test_pasted_keys_survive_a_line_break(client):
    """Keys are handed over in chat messages, which wrap them, so a paste commonly arrives
    with whitespace in the middle. The first real user hit exactly that and was told their
    correct key was rejected. A worker key is token_urlsafe output and can never contain
    whitespace, so the page strips it rather than making the reader spot a line break."""
    asset = client.get("/api/v1/docs-assets/docs-shell.js").text
    assert 'replace(/\\s+/g, "")' in asset
    # nothing on a request path may use the raw field value
    for line in asset.splitlines():
        if "X-Api-Key" in line:
            assert "keyField.value" not in line, line


def test_no_sourcemap_request_is_provoked(client):
    """The upstream CSS points at a .map we do not vendor, so every visit with devtools open
    logged a 404. A console error on a docs page reads as a broken page."""
    css = client.get("/api/v1/docs-assets/swagger-ui.css").text
    assert "sourceMappingURL" not in css
    assert client.get("/api/v1/docs-assets/swagger-ui.css.map").status_code == 404
