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
