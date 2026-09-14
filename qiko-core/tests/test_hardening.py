from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import RateLimitMiddleware, RequestSizeLimitMiddleware
from app.core.ratelimit import InMemoryRateLimiter, RedisRateLimiter


# --- rate limiter unit ---
def test_inmemory_rate_limiter():
    rl = InMemoryRateLimiter(limit=2, window_seconds=60)
    assert rl.allow("k") is True
    assert rl.allow("k") is True
    assert rl.allow("k") is False
    assert rl.allow("other") is True  # separate key


def test_rate_limiter_window_reset():
    rl = InMemoryRateLimiter(limit=1, window_seconds=0)  # window immediately expired
    assert rl.allow("k") is True
    assert rl.allow("k") is True  # window reset each call


async def test_redis_rate_limiter_uses_atomic_shared_counter():
    class FakeRedis:
        async def eval(self, script, keys, key, limit, window):
            assert "INCR" in script and keys == 1 and key.endswith(":shared")
            assert limit == 2 and window == 60
            return 1

    limiter = RedisRateLimiter(redis=FakeRedis(), namespace="rate", limit=2, window_seconds=60)
    assert await limiter.allow("shared") is True


# --- security headers on the real app ---
def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in r.headers
    assert "Content-Security-Policy" in r.headers


def test_cors_allows_configured_origin(client):
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --- middleware integration (dedicated small apps) ---
def _app_with(mw_cls, **kw):
    app = FastAPI()
    app.add_middleware(mw_cls, **kw)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.post("/echo")
    def echo(body: dict):
        return body

    return TestClient(app)


def test_rate_limit_middleware_returns_429():
    c = _app_with(RateLimitMiddleware, limiter=InMemoryRateLimiter(limit=2))
    assert c.get("/ping").status_code == 200
    assert c.get("/ping").status_code == 200
    assert c.get("/ping").status_code == 429


def test_rate_limit_middleware_strict_path_gets_tighter_budget():
    # /ping falls under the generic (generous) limit; /echo is a "login-like" strict path with
    # its own much smaller budget, even though both share the same generic limiter headroom.
    c = _app_with(RateLimitMiddleware, limiter=InMemoryRateLimiter(limit=100),
                 strict_limiter=InMemoryRateLimiter(limit=1), strict_paths=("/echo",))
    assert c.get("/ping").status_code == 200
    assert c.get("/ping").status_code == 200  # generic limit (100) not remotely hit
    assert c.post("/echo", json={}).status_code == 200
    assert c.post("/echo", json={}).status_code == 429  # strict limit (1) hit on the 2nd call


def test_login_endpoint_has_its_own_strict_rate_limit(client):
    # Regression guard for the real app wiring, not just the middleware unit: /auth/login must be
    # in the configured strict_paths, not just covered by the generous global default.
    from app.core.config import get_settings

    assert get_settings().auth_rate_limit_per_minute < get_settings().rate_limit_per_minute
    limit = get_settings().auth_rate_limit_per_minute
    responses = [client.post("/api/v1/auth/login", json={"email": "x" + "@" + "x.com", "password": "wrong"})
                for _ in range(limit + 2)]
    assert responses[-1].status_code == 429
    assert any(r.status_code == 401 for r in responses[:limit])  # legit attempts still 401, not 429


def test_request_size_limit_middleware():
    c = _app_with(RequestSizeLimitMiddleware, max_bytes=10)
    assert c.post("/echo", json={"x": "y"}).status_code == 200         # small
    assert c.post("/echo", json={"x": "y" * 100}).status_code == 413   # too large


async def test_request_size_limit_counts_streamed_body_without_content_length():
    messages = iter([
        {"type": "http.request", "body": b"123456", "more_body": True},
        {"type": "http.request", "body": b"789012", "more_body": False},
    ])
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        while (await receive()).get("more_body"):
            pass

    middleware = RequestSizeLimitMiddleware(downstream, max_bytes=10)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": "/echo", "raw_path": b"/echo",
             "query_string": b"", "headers": [], "client": ("test", 1), "server": ("test", 80)}
    await middleware(scope, receive, send)
    assert sent[0]["status"] == 413


def test_live_edge_sends_hsts_with_preload_and_admin_hides_its_stack():
    """Rows 6 and 14 of the Essential Living security review.

    Row 14 needs the `preload` directive on every live site before qiko.ai can be submitted to
    hstspreload.org; it was missing while the older V1 hosts already sent it. Row 6 is a stack
    disclosure: the admin app leaked `x-powered-by: Next.js` because only the creator app set
    poweredByHeader:false. Pinned here so neither silently regresses.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    live = (root / "Caddyfile.live").read_text()
    hsts = [line.strip() for line in live.splitlines() if "Strict-Transport-Security" in line]
    assert hsts, "the live edge must set HSTS"
    for line in hsts:
        assert "includeSubDomains" in line and "preload" in line, line

    for app in ("admin", "creator"):
        config = (root / "frontend/apps" / app / "next.config.mjs").read_text()
        assert "poweredByHeader: false" in config, f"{app} must not advertise its stack"


# --- a partner origin may read responses without becoming CSRF-trusted (QIKO-1102) ------------


def _partner_settings(monkeypatch, target: str, **overrides):
    """Point one module's get_settings at a throwaway Settings carrying a partner origin.

    Deliberately patches the caller's reference rather than clearing get_settings' lru_cache:
    conftest mutates the cached Settings instance in place (slack credentials, token TTL), so
    evicting it makes unrelated tests later in the session see a fresh object without any of
    that, which is a failure with no connection to the test that caused it.
    """
    from app.core.config import Settings

    settings = Settings(cors_allow_origins=["http://localhost:3000"],
                        partner_cors_origins=["https://panel.partner.example"], **overrides)
    monkeypatch.setattr(f"{target}.get_settings", lambda: settings)
    return settings


def test_partner_origin_is_allowed_by_cors(monkeypatch):
    """The CORS half of the split: their browser may read the response."""
    from app.main import create_app

    _partner_settings(monkeypatch, "app.main")
    c = TestClient(create_app())

    r = c.get("/health", headers={"Origin": "https://panel.partner.example"})
    assert r.headers.get("access-control-allow-origin") == "https://panel.partner.example"

    # An origin in neither list is still refused, so the split did not open the door generally.
    r = c.get("/health", headers={"Origin": "https://unknown.example"})
    assert r.headers.get("access-control-allow-origin") is None


def test_partner_origin_is_still_rejected_by_csrf(monkeypatch):
    """The half that matters. Being readable in a browser must not make an origin acceptable as
    the source of a state-changing request carrying an admin's session cookie. Before the split
    there was one list, so allowing the CORS read above would have granted this too."""
    import pytest
    from fastapi import HTTPException, Request

    from app.modules.identity.csrf import CSRF_COOKIE, CSRF_HEADER, require_csrf

    # Must be a non-dev environment: require_csrf deliberately skips the origin check in dev, so
    # asserting a rejection under the default settings would pass for the wrong reason.
    _partner_settings(monkeypatch, "app.modules.identity.csrf", environment="preprod")

    def _request(origin: str) -> Request:
        token = "a-csrf-token-value"
        return Request({
            "type": "http", "method": "POST", "path": "/admin/anything",
            "headers": [(CSRF_HEADER.encode(), token.encode()),
                        (b"cookie", f"{CSRF_COOKIE}={token}".encode()),
                        (b"origin", origin.encode())],
        })

    # A first-party origin passes, as before.
    require_csrf(_request("http://localhost:3000"))

    # The partner origin does not, even though CORS allows it to read.
    with pytest.raises(HTTPException) as first_party_only:
        require_csrf(_request("https://panel.partner.example"))
    assert first_party_only.value.status_code == 403
    assert first_party_only.value.detail == "Request origin rejected"
