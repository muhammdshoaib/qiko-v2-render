from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import RateLimitMiddleware, RequestSizeLimitMiddleware
from app.core.ratelimit import InMemoryRateLimiter


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


def test_request_size_limit_middleware():
    c = _app_with(RequestSizeLimitMiddleware, max_bytes=10)
    assert c.post("/echo", json={"x": "y"}).status_code == 200         # small
    assert c.post("/echo", json={"x": "y" * 100}).status_code == 413   # too large
