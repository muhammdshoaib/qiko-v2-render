from fastapi.testclient import TestClient

from app.main import create_app


def test_lifespan_builds_sessionmaker():
    # Entering the TestClient context runs the FastAPI lifespan (engine + sessionmaker on app.state).
    with TestClient(create_app()) as client:
        assert client.app.state.sessionmaker is not None
        assert client.app.state.engine is not None
