from app.core.config import Settings


def test_environment_drives_debug_and_production_gates():
    # Behaviour that matters: only dev exposes debug affordances; only live is production.
    assert Settings(environment="dev").debug is True
    assert Settings(environment="dev").is_production is False
    assert Settings(environment="preprod").debug is False
    assert Settings(environment="live").is_production is True
    assert Settings(environment="live").debug is False
