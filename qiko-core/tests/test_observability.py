import json
import logging

from app.core import observability
from app.core.logging import JsonFormatter


def test_request_id_generated_and_returned(client):
    r = client.get("/health")
    assert r.headers.get("X-Request-Id")  # generated when none supplied


def test_inbound_request_id_is_propagated(client):
    r = client.get("/health", headers={"X-Request-Id": "trace-abc"})
    assert r.headers["X-Request-Id"] == "trace-abc"


def test_log_record_includes_request_id():
    token = observability._request_id.set("rid-123")
    try:
        rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
        out = json.loads(JsonFormatter().format(rec))
        assert out["request_id"] == "rid-123"
    finally:
        observability._request_id.reset(token)
