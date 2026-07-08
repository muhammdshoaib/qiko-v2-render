import builtins

from app.core.observability import init_sentry, init_tracing


def test_init_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: type("S", (), {"sentry_dsn": ""})())
    assert init_sentry() is False


def test_init_sentry_does_not_crash_when_package_missing(monkeypatch):
    """SENTRY_DSN configured but the sentry-sdk package not installed must degrade gracefully,
    not raise ModuleNotFoundError and take the whole app down at startup."""
    monkeypatch.setattr("app.core.config.get_settings", lambda: type("S", (), {"sentry_dsn": "https://x@sentry.io/1"})())
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("no module named sentry_sdk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert init_sentry() is False


def test_init_tracing_does_not_crash_when_package_missing(monkeypatch):
    """OTel packages not installed must degrade gracefully, not raise ModuleNotFoundError."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError("no module named opentelemetry")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        assert init_tracing(app=None) is False
    finally:
        builtins.__import__ = real_import
