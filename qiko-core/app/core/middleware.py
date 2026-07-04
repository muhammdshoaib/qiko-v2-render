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
    def __init__(self, app, *, limiter: RateLimiter) -> None:
        super().__init__(app)
        self.limiter = limiter

    def _key(self, request: Request) -> str:
        client = request.client.host if request.client else "unknown"
        return f"{client}:{request.url.path}"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.limiter.allow(self._key(request)):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)
