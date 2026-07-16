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
    # a real secret is accepted in a non-dev environment.
    Settings(environment="live", session_secret="a-real-strong-secret").assert_secrets_set()
