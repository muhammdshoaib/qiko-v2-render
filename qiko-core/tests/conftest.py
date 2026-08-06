import pytest
from fastapi.testclient import TestClient

from app.main import create_app


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
