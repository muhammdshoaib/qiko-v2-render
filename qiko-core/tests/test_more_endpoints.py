import io

from tests.helpers import auth_cookies

C = auth_cookies("more", "owner")
ISO = "IDG holds a current ISO 9001 certification valid through 2027."


def test_knowledge_ingest_file_and_evaluate(client):
    r = client.post("/api/v1/knowledge/ingest-file", data={"doc_id": "rfp1"},
                    files={"file": ("rfp.txt", ISO, "text/plain")}, cookies=C)
    assert r.status_code == 200 and r.json()["chunks"] >= 1
    assert client.get("/api/v1/knowledge/rfp-criteria", cookies=C).json()["criteria"]
    ev = client.post("/api/v1/knowledge/evaluate",
                     json={"doc_id": "rfp1", "criterion": "Are certifications evidenced?", "topic": "rfp"}, cookies=C).json()
    assert "ISO 9001" in ev["answer"] and "decision" in ev


def _wb() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["region", "revenue"])
    ws.append(["EMEA", 120000])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_upload_analytics_report(client):
    up = client.post("/api/v1/excel/upload", data={"source_name": "q3"},
                     files={"file": ("q3.xlsx", _wb(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, cookies=C)
    assert up.json()["records"] == 1
    a = client.post("/api/v1/excel/analytics", json={"rows": [["region", "revenue"], ["EMEA", 120000], ["APAC", 90000]]}, cookies=C).json()
    assert a["columns"]["revenue"]["sum"] == 210000
    rep = client.post("/api/v1/excel/report", json={"source": "q3", "analytics": a, "fmt": "xlsx"}, cookies=C).json()
    assert rep["key"].endswith(".xlsx")


def test_signal_buckets_recs_export(client):
    assert client.get("/api/v1/signal/buckets/s1", cookies=C).status_code == 200
    assert client.get("/api/v1/signal/recommendations/s1", cookies=C).json() == []
    assert client.post("/api/v1/signal/export/s1", cookies=C).json()["url"].endswith(".pdf")


def test_voice_web_call_config(client):
    cfg = client.get("/api/v1/voice/web-call-config", cookies=C).json()
    assert cfg["provider"] == "bedrock-nova-sonic" and "key" not in str(cfg).lower()
