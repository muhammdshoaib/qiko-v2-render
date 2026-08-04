"""Security middleware: response security headers, request-size cap, and rate limiting."""
from __future__ import annotations

import inspect
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.ratelimit import RateLimiter

logger = logging.getLogger(__name__)

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


class _RequestTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    def __init__(self, app, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length", b"").decode()
        if content_length.isdigit() and int(content_length) > self.max_bytes:
            await JSONResponse({"detail": "Request entity too large"}, status_code=413)(scope, receive, send)
            return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await JSONResponse({"detail": "Request entity too large"}, status_code=413)(scope, receive, send)


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

    async def _allowed(self, limiter: RateLimiter, key: str) -> bool:
        """Fail OPEN. Rate limiting is a protection, not a correctness requirement: if the backing
        Redis is unreachable (restart, maxmemory under noeviction, AOF stall, partition) we must not
        turn a limiter outage into a 500 on every request -- this middleware wraps every route,
        including /health, so an exception here is a total outage."""
        try:
            result = limiter.allow(key)
            return await result if inspect.isawaitable(result) else result
        except Exception:  # noqa: BLE001 - any limiter/backend failure must not block traffic
            logger.warning("rate_limit_backend_unavailable_failing_open")
            return True

    async def dispatch(self, request: Request, call_next) -> Response:
        key = self._key(request)
        if not await self._allowed(self.limiter, key):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        if self.strict_limiter and request.url.path.startswith(self.strict_paths):
            if not await self._allowed(self.strict_limiter, key):
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)
