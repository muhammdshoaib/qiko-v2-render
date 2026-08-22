import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

# Applied at IMPORT, not in a fixture, because four test modules mint auth cookies at module level and
# pytest imports those modules during collection, before any fixture runs. A session fixture therefore
# raised the TTL just too late to matter.
#
# The property worth having is that the suite's own runtime cannot decide whether it passes. With the
# production TTL of 900 seconds it passed only while it finished inside fifteen minutes; once it grew
# past that, a dozen tests started failing with "invalid or expired token" in ways that looked like a
# real regression and reproduced nowhere in isolation. Token expiry itself stays covered by
# tests/test_identity_units.py::test_expired_token_rejected, which builds its own expired token.
get_settings().access_token_ttl_seconds = 24 * 60 * 60
get_settings().slack_client_id = "test-slack-client-id"
get_settings().slack_client_secret = "test-slack-client-secret"
get_settings().slack_redirect_uri = "http://localhost:8000/api/v1/channels/slack/callback"


@pytest.fixture(autouse=True)
def _isolated_identity_store():
    """Give every test a fresh in-memory user store.

    `app/modules/identity/router.py` holds the store in a MODULE-LEVEL global that `create_app` does
    not reset, so users seeded by one test file were visible to every test that ran after it. That is
    invisible until two files disagree: a directory test asserting an exact set of emails passed only
    because no other file happened to seed a user, and a 2FA test authenticating as a fixed user id
    broke the moment another file planted a row with that id and a different password.

    Resetting here rather than fixing each assertion, because the shared global is the actual defect
    and a per-assertion workaround would leave the next collision to be discovered by CI order.
    """
    from app.modules.identity import router as identity_router
    from app.modules.identity.store import seeded_store

    previous = identity_router._store
    identity_router._store = seeded_store()
    try:
        yield
    finally:
        identity_router._store = previous


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
