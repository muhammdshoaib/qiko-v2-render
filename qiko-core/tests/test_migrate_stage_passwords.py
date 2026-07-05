from app.modules.identity.security import verify_password
from scripts.migrate_stage import make_password_hasher


def test_preprod_mode_returns_the_same_shared_password_for_every_user():
    hasher = make_password_hasher(live_mode=False, preprod_pw="preprod-test")
    h1, h2 = hasher(), hasher()
    assert h1 == h2
    assert verify_password("preprod-test", h1)
    assert verify_password("preprod-test", h2)


def test_live_mode_returns_a_unique_unusable_hash_per_user():
    hasher = make_password_hasher(live_mode=True, preprod_pw="preprod-test")
    h1, h2 = hasher(), hasher()
    assert h1 != h2  # each user gets their own random secret
    # nobody -- including the shared test password -- can log in with it
    assert not verify_password("preprod-test", h1)
    assert not verify_password("", h1) if h1 else True
