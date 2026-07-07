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

    def fake_get_provider():
        class P:
            def generate(self, prompt, *, system=None, temperature=0.2):
                from app.modules.ai.gateway import LLMResponse
                return LLMResponse(text=payload)
        return P()

    return c, pack, fake_get_provider


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
