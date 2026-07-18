import pytest

from app.core.config import DEFAULT_SESSION_SECRET, Settings


def test_environment_drives_debug_and_production_gates():
    # Behaviour that matters: only dev exposes debug affordances; only live is production.
    assert Settings(environment="dev").debug is True
    assert Settings(environment="dev").is_production is False
    assert Settings(environment="preprod").debug is False
    assert Settings(environment="live").is_production is True
    assert Settings(environment="live").debug is False


def test_assert_secrets_set_fails_closed_on_default_secret_in_non_dev():
    # dev keeps the forgeable default working (dev/test convenience).
    Settings(environment="dev", session_secret=DEFAULT_SESSION_SECRET).assert_secrets_set()
    # a non-dev deploy must refuse to start on the default -- it could otherwise silently sign and
    # verify tokens with a key anyone can read from source.
    for env in ("preprod", "live"):
        with pytest.raises(RuntimeError, match="session_secret"):
            Settings(environment=env, session_secret=DEFAULT_SESSION_SECRET).assert_secrets_set()
    # a real secret is accepted in a non-dev environment (with prod-safe stores/backend).
    Settings(environment="live", session_secret="a-real-strong-secret",
             use_db_stores=True, task_backend="arq").assert_secrets_set()


def _prod_settings(**overrides):
    base = dict(session_secret="a-real-strong-secret", use_db_stores=True, task_backend="arq")
    base.update(overrides)
    return Settings(**base)


def test_assert_secrets_set_requires_prod_safe_stores_and_backend_in_non_dev():
    # dev is unaffected: the in-memory stores + inline backend defaults are fine for dev/tests.
    Settings(environment="dev").assert_secrets_set()

    for env in ("preprod", "live"):
        # in-memory stores would silently drop all data on every restart.
        with pytest.raises(RuntimeError, match="USE_DB_STORES"):
            _prod_settings(environment=env, use_db_stores=False).assert_secrets_set()
        # the inline (eager) backend would run the 30-min generation inline and hit the LB timeout.
        with pytest.raises(RuntimeError, match="TASK_BACKEND"):
            _prod_settings(environment=env, task_backend="eager").assert_secrets_set()
        # a fully prod-safe config boots.
        _prod_settings(environment=env).assert_secrets_set()
