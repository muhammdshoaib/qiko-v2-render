import io

from app.modules.ai.gateway import LLMResponse

from tests.helpers import auth_cookies

TENDER_TEXT = "Submission deadline is 2026-08-01. Format: sealed electronic submission via portal."


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2):
        return LLMResponse(text=self.text)


def test_ask_requires_document_first(client):
    c = auth_cookies("bidctx1", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/ask", cookies=c, json={"question": "When is it due?"})
    assert r.status_code == 422


def test_extract_persists_document_text_for_later_ask(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider",
                        lambda **_kw: _CannedProvider('[{"id":"A1","title":"Deadline","classification":"KB","requirement":"State the deadline."}]'))
    c = auth_cookies("bidctx2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
               files={"file": ("t.txt", io.BytesIO(TENDER_TEXT.encode()), "text/plain")})

    monkeypatch.setattr("app.modules.rfp.router.get_provider",
                        lambda **_kw: _CannedProvider("The submission deadline is 2026-08-01."))
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/ask", cookies=c, json={"question": "When is it due?"})
    assert r.status_code == 200
    assert "2026-08-01" in r.json()["answer"]


def test_ask_404_for_missing_pack(client):
    c = auth_cookies("bidctx3", "owner")
    r = client.post("/api/v1/rfp/packs/missing/ask", cookies=c, json={"question": "x"})
    assert r.status_code == 404
