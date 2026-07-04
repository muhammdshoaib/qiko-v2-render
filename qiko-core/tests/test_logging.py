import json
import logging

from app.core import tenancy
from app.core.logging import JsonFormatter, configure_logging


def _record(msg="hello", exc_info=None):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, exc_info)


def test_formatter_basic():
    out = json.loads(JsonFormatter().format(_record()))
    assert out["level"] == "INFO"
    assert out["msg"] == "hello"
    assert "tenant" not in out


def test_formatter_includes_tenant():
    token = tenancy.set_tenant("acme")
    try:
        out = json.loads(JsonFormatter().format(_record()))
        assert out["tenant"] == "acme"
    finally:
        tenancy.reset_tenant(token)


def test_formatter_includes_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        out = json.loads(JsonFormatter().format(_record(exc_info=sys.exc_info())))
    assert "boom" in out["exc"]


def test_configure_logging_sets_level_and_handler():
    configure_logging("DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
