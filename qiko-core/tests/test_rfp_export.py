import io

from tests.helpers import auth_cookies

ISO = "IDG holds a current ISO 9001 certification valid through 2027, verified annually."


def _setup_pack_with_requirements(client, tenant: str):
    c = auth_cookies(tenant, "owner")
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=c)
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender"}, cookies=c).json()

    import json as _json
    payload = _json.dumps([
        {"id": "A1", "title": "ISO Certification", "classification": "KB",
         "requirement": "Describe your ISO 9001 certification."},
        {"id": "A2", "title": "Pricing", "classification": "MANUAL", "requirement": "Complete pricing schedule."},
    ])

    def fake_get_provider(**_kwargs):
        class P:
            def generate(self, prompt, *, system=None, temperature=0.2):
                from app.modules.ai.gateway import LLMResponse
                return LLMResponse(text=payload)
        return P()

    return c, pack, fake_get_provider


def test_extract_enforces_upload_cap(client, monkeypatch):
    # A tender upload larger than the per-endpoint cap is refused with 413 (shrink the cap so the
    # test payload stays small and never trips the global request-size middleware first).
    monkeypatch.setattr("app.modules.rfp.router.MAX_UPLOAD_BYTES", 16)
    c = auth_cookies("extrcap1", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                    files={"file": ("t.txt", io.BytesIO(b"x" * 64), "text/plain")})
    assert r.status_code == 413


def test_export_requires_extracted_requirements_first(client):
    c = auth_cookies("exportco0", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender"}, cookies=c).json()
    assert client.get(f"/api/v1/rfp/packs/{pack['id']}/export/xlsx", cookies=c).status_code == 404


def test_export_xlsx_has_grounding_column_and_status(client, monkeypatch):
    c, pack, fake_get_provider = _setup_pack_with_requirements(client, "exportco1")
    monkeypatch.setattr("app.modules.rfp.router.get_provider", fake_get_provider)
    client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
               files={"file": ("t.txt", io.BytesIO(b"tender text"), "text/plain")})

    r = client.get(f"/api/v1/rfp/packs/{pack['id']}/export/xlsx", cookies=c)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.active
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    assert "Grounding %" in header
    assert "Status" in header
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(rows) == 2
    # A2 is MANUAL -> not drafted by AI, note says so
    manual_row = next(r for r in rows if r[0] == "A2")
    assert "team" in manual_row[5].lower()


def test_get_answers_json_for_cockpit(client, monkeypatch):
    c, pack, fake_get_provider = _setup_pack_with_requirements(client, "exportco1b")
    monkeypatch.setattr("app.modules.rfp.router.get_provider", fake_get_provider)
    client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
               files={"file": ("t.txt", io.BytesIO(b"tender text"), "text/plain")})

    r = client.get(f"/api/v1/rfp/packs/{pack['id']}/answers", cookies=c)
    assert r.status_code == 200
    answers = r.json()
    assert len(answers) == 2
    kb = next(a for a in answers if a["req_id"] == "A1")
    assert kb["classification"] == "KB" and kb["answer"] and "confidence" in kb and "citations" in kb
    manual = next(a for a in answers if a["req_id"] == "A2")
    assert manual["answer"] == "" and "team" in manual["note"].lower()


def test_answers_are_cached_and_force_bypasses_cache(client, monkeypatch):
    c = auth_cookies("cacheco1", "owner")
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=c)
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender"}, cookies=c).json()
    payload = '[{"id": "A1", "title": "ISO Certification", "classification": "KB", "requirement": "Describe your ISO 9001 certification."}]'
    calls = {"n": 0}

    def counting_provider(**_kwargs):
        class P:
            def generate(self, prompt, *, system=None, temperature=0.2):
                if "TENDER DOCUMENT" in prompt and "REQUIREMENT" not in prompt:
                    from app.modules.ai.gateway import LLMResponse
                    return LLMResponse(text=payload)
                calls["n"] += 1
                from app.modules.ai.gateway import LLMResponse
                return LLMResponse(text="cached answer text")
        return P()

    monkeypatch.setattr("app.modules.rfp.router.get_provider", counting_provider)
    # worker.answer() -> AgentCore -> Generator builds its own provider via a separately imported
    # get_provider() reference -- patch that one too so the answer-generation call is also faked.
    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", counting_provider)
    client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
               files={"file": ("t.txt", io.BytesIO(b"tender text"), "text/plain")})

    first = client.get(f"/api/v1/rfp/packs/{pack['id']}/answers", cookies=c).json()
    calls_after_first = calls["n"]
    assert calls_after_first > 0  # A1 is a KB item -- one real generation

    second = client.get(f"/api/v1/rfp/packs/{pack['id']}/answers", cookies=c).json()
    assert calls["n"] == calls_after_first  # served from cache, no new LLM calls
    assert second == first

    client.get(f"/api/v1/rfp/packs/{pack['id']}/answers?force=true", cookies=c)
    assert calls["n"] > calls_after_first  # force= bypasses the cache


def test_feedback_approve_and_reject(client):
    c = auth_cookies("fbco1", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender"}, cookies=c).json()

    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=c,
                    json={"req_id": "B1", "decision": "Approve", "comment": "Human-approved answer text."})
    assert r.status_code == 200
    assert r.json() == {"req_id": "B1", "decision": "Approve", "saved": True}

    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=c,
                    json={"req_id": "B1", "decision": "Reject"})
    assert r.status_code == 200 and r.json()["decision"] == "Reject"


def test_feedback_rejects_invalid_decision(client):
    c = auth_cookies("fbco2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=c,
                    json={"req_id": "B1", "decision": "Bogus"})
    assert r.status_code == 422


def test_feedback_requires_editor_role(client):
    # A viewer must not be able to plant "verified ground truth" into the tenant's knowledge
    # base -- writing feedback needs the same Editor-or-above bar as every other mutation.
    owner = auth_cookies("fbco3", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender"}, cookies=owner).json()
    viewer = auth_cookies("fbco3", "viewer")
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=viewer,
                    json={"req_id": "B1", "decision": "Approve", "comment": "should be blocked"})
    assert r.status_code == 403


def test_feedback_404s_for_nonexistent_pack(client):
    c = auth_cookies("fbco4", "owner")
    r = client.post("/api/v1/rfp/packs/does-not-exist/feedback", cookies=c,
                    json={"req_id": "B1", "decision": "Approve", "comment": "text"})
    assert r.status_code == 404


def test_force_regenerate_answers_requires_editor_role(client, monkeypatch):
    c, pack, fake_get_provider = _setup_pack_with_requirements(client, "fbco5")
    monkeypatch.setattr("app.modules.rfp.router.get_provider", fake_get_provider)
    client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
               files={"file": ("t.txt", io.BytesIO(b"tender text"), "text/plain")})

    viewer = auth_cookies("fbco5", "viewer")
    r = client.get(f"/api/v1/rfp/packs/{pack['id']}/answers", params={"force": "true"}, cookies=viewer)
    assert r.status_code == 403
    # a plain (non-forced) read stays available to a viewer
    r2 = client.get(f"/api/v1/rfp/packs/{pack['id']}/answers", cookies=viewer)
    assert r2.status_code == 200


def test_export_docx_clean_and_review(client, monkeypatch):
    c, pack, fake_get_provider = _setup_pack_with_requirements(client, "exportco2")
    monkeypatch.setattr("app.modules.rfp.router.get_provider", fake_get_provider)
    client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
               files={"file": ("t.txt", io.BytesIO(b"tender text"), "text/plain")})

    clean = client.get(f"/api/v1/rfp/packs/{pack['id']}/export/docx-clean", cookies=c)
    assert clean.status_code == 200
    assert clean.headers["content-type"].startswith("application/vnd.openxmlformats")

    from docx import Document
    doc = Document(io.BytesIO(clean.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "ISO Certification" in text
    assert "[To be completed by the team" in text  # MANUAL section placeholder

    review = client.get(f"/api/v1/rfp/packs/{pack['id']}/export/docx-review", cookies=c)
    assert review.status_code == 200
    review_doc = Document(io.BytesIO(review.content))
    review_text = "\n".join(p.text for p in review_doc.paragraphs)
    assert "Requirement:" in review_text
