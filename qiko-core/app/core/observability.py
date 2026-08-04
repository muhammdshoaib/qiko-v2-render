"""Request correlation + observability hooks.

Every request gets a request id (propagated from an inbound X-Request-Id or generated), bound into
the logging context alongside the tenant, and echoed on the response. Traces/metrics/Sentry
exporters are initialised here behind config; the exporter wiring itself is deployment config.
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = _request_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


def init_sentry() -> bool:  # pragma: no cover - requires the sentry SDK + DSN
    from app.core.config import get_settings

    dsn = getattr(get_settings(), "sentry_dsn", "")
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but the sentry-sdk package isn't installed; skipping init")
        return False

    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1, max_request_body_size="never",
                    include_local_variables=False)
    return True


def init_tracing(app) -> bool:  # pragma: no cover - requires the OTel SDK + collector
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        logger.warning("OTEL_ENABLED is set but opentelemetry packages aren't installed; skipping init")
        return False

    FastAPIInstrumentor.instrument_app(app)
    return True
