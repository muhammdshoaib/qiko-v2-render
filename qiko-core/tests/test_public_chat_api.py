"""Public (no-auth) chat API: agentic-first, only serves a ready worker."""
from tests.helpers import auth_cookies

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


def _make_ready_worker(client) -> str:
    c = auth_cookies("pubco", "owner")
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=c)
    agent = client.post("/api/v1/agents", json={"name": "IDG", "plan": "free"}, cookies=c).json()
    client.post(f"/api/v1/agents/{agent['id']}/ready", cookies=c)
    return agent["id"]


def test_public_chat_answers_when_ready_no_auth(client):
    wid = _make_ready_worker(client)
    # no auth cookie — public endpoint
    r = client.post("/api/v1/public/chat", json={
        "tenant": "pubco", "worker_id": wid, "question": "Describe your ISO 9001 certification."})
    assert r.status_code == 200 and r.json()["role"] == "assistant" and "ISO 9001" in r.json()["text"]


def test_public_chat_404_unknown_worker(client):
    assert client.post("/api/v1/public/chat",
                       json={"tenant": "pubco", "worker_id": "nope", "question": "hi"}).status_code == 404


def test_public_chat_403_when_not_ready(client):
    c = auth_cookies("pubco2", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Draft", "plan": "free"}, cookies=c).json()
    r = client.post("/api/v1/public/chat",
                    json={"tenant": "pubco2", "worker_id": agent["id"], "question": "hi"})
    assert r.status_code == 403  # worker not ready
