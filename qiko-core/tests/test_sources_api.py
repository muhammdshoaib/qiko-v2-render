"""Worker knowledge-sources API: structured sources feed the worker's grounded knowledge."""
from tests.helpers import auth_cookies

C = auth_cookies("srcco", "owner")


async def _fake_fetch(url: str) -> str:
    return "We provide ISO 9001 certified quality audits."


def test_add_sources_and_they_are_searchable(client):
    client.app.state.sources.fetch_url = _fake_fetch
    base = "/api/v1/agents/ag1/sources"
    assert client.post(f"{base}/behaviors", json={"source_id": "1", "text": "Always greet politely."}, cookies=C).status_code == 200
    assert client.post(f"{base}/faqs", json={"source_id": "1", "question": "ISO?", "answer": "Yes, ISO 9001 through 2027."}, cookies=C).status_code == 200
    client.post(f"{base}/policies", json={"source_id": "1", "title": "Refunds", "body": "30 days."}, cookies=C)
    client.post(f"{base}/websites", json={"source_id": "1", "name": "IDG", "url": "https://idg.example", "details": "Audits."}, cookies=C)
    client.put(f"{base}/persona", json={"fields": {"full_name": "IDG Assistant"}}, cookies=C)

    # the sources are ingested into knowledge and searchable
    hits = client.post("/api/v1/knowledge/search", json={"query": "ISO 9001"}, cookies=C).json()["results"]
    assert any("ISO 9001" in h for h in hits)
    docs = {d["doc_id"] for d in client.get("/api/v1/knowledge/documents", cookies=C).json()}
    assert "ag1-behavior-1" in docs and "ag1-faq-1" in docs and "ag1-website-1" in docs and "ag1-persona-core" in docs


def test_delete_source(client):
    base = "/api/v1/agents/ag2/sources"
    client.post(f"{base}/behaviors", json={"source_id": "9", "text": "temp"}, cookies=C)
    assert client.request("DELETE", f"{base}/behavior/9", cookies=C).json()["removed"] >= 1


def test_sources_require_editor_role(client):
    r = client.post("/api/v1/agents/ag3/sources/behaviors",
                    json={"source_id": "1", "text": "x"}, cookies=auth_cookies("srcco", "viewer"))
    assert r.status_code == 403
