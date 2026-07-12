"""Security middleware: response security headers, request-size cap, and rate limiting."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.ratelimit import RateLimiter

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return JSONResponse({"detail": "Request entity too large"}, status_code=413)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """A single global per-path budget is far too permissive for brute-force-sensitive endpoints
    (login, password reset, OTP): `strict_limiter` applies a much tighter budget to any request
    path starting with one of `strict_paths`, falling back to `limiter` for everything else."""

    def __init__(self, app, *, limiter: RateLimiter, strict_limiter: RateLimiter | None = None,
                strict_paths: tuple[str, ...] = ()) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.strict_limiter = strict_limiter
        self.strict_paths = strict_paths

    def _key(self, request: Request) -> str:
        client = request.client.host if request.client else "unknown"
        return f"{client}:{request.url.path}"

    async def dispatch(self, request: Request, call_next) -> Response:
        key = self._key(request)
        if not self.limiter.allow(key):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        if self.strict_limiter and request.url.path.startswith(self.strict_paths):
            if not self.strict_limiter.allow(key):
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)
