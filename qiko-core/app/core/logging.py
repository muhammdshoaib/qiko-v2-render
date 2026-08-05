"""Structured JSON logging, configured once at startup."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.observability import get_request_id
from app.core.tenancy import get_tenant


# Everything LogRecord sets itself; anything else on the record came from `extra`.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        tenant = get_tenant()
        if tenant:
            payload["tenant"] = tenant
        rid = get_request_id()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Merge the diagnostic context passed as logger.warning(..., extra={...}). It used to be
        # dropped entirely, so every diagnostic in the codebase logged a bare message with the
        # tenant, source and error stripped out -- and with LOG_LEVEL=WARNING and no Sentry DSN in
        # production, that left almost nothing to investigate an incident with.
        for key, value in record.__dict__.items():
            if key in _RESERVED or key in payload:
                continue
            payload[key] = value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
