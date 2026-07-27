"""Public (no-auth) chat API: agentic-first, only serves a ready worker."""
from app.core.config import Environment, get_settings
from app.modules.ai.gateway import LLMResponse
from tests.helpers import auth_cookies

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


def _make_ready_worker(client) -> str:
    c = auth_cookies("pubco", "owner")
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=c)
    agent = client.post("/api/v1/agents", json={"name": "IDG", "plan": "free"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/ready", cookies=c)
    return agent["id"]


def test_public_chat_is_disabled_by_default_outside_dev(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", Environment.preprod)
    monkeypatch.setattr(settings, "public_chat_enabled", False)

    response = client.post("/api/v1/public/chat", json={
        "tenant": "pubco", "worker_id": "worker-1", "question": "hello"})

    assert response.status_code == 404 and response.json() == {"detail": "not found"}


def test_public_chat_answers_when_ready_no_auth(client, monkeypatch):
    class Provider:
        def generate(self, prompt, **_kwargs):
            return LLMResponse(text=prompt, model="test", stub=False)

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", lambda: Provider())
    wid = _make_ready_worker(client)
    # no auth cookie — public endpoint
    r = client.post("/api/v1/public/chat", json={
        "tenant": "pubco", "worker_id": wid, "question": "Describe your ISO 9001 certification."})
    assert r.status_code == 200 and r.json()["role"] == "assistant" and "ISO 9001" in r.json()["text"]


def test_public_chat_rejects_unbounded_prompt_and_studio(client):
    assert client.post("/api/v1/public/chat", json={
        "tenant": "pubco", "worker_id": "worker-1", "question": "x" * 4001,
    }).status_code == 422
    assert client.post("/api/v1/public/chat", json={
        "tenant": "pubco", "worker_id": "worker-1", "question": "hi",
        "studio": {"unexpected": "data"},
    }).status_code == 422


def test_public_chat_404_unknown_worker(client):
    assert client.post("/api/v1/public/chat",
                       json={"tenant": "pubco", "worker_id": "nope", "question": "hi"}).status_code == 404


def test_public_chat_403_when_not_ready(client):
    c = auth_cookies("pubco2", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Draft", "plan": "free"}, cookies=c).json()
    r = client.post("/api/v1/public/chat",
                    json={"tenant": "pubco2", "worker_id": agent["id"], "question": "hi"})
    assert r.status_code == 403  # worker not ready
