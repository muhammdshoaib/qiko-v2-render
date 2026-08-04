import io

import pytest

from app.core.config import Environment, get_settings
from app.modules.ai.gateway import LLMResponse
from app.modules.voice.pipeline import UnavailableSpeechGateway
from app.main import create_app
from tests.helpers import auth_cookies

def _cookies():
    return auth_cookies("more", "owner")
ISO = "IDG holds a current ISO 9001 certification valid through 2027."


@pytest.fixture(autouse=True)
def _non_stub_provider(monkeypatch):
    class Provider:
        def generate(self, prompt, **_kwargs):
            return LLMResponse(text=prompt, model="test", stub=False)

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", lambda: Provider())


def test_knowledge_ingest_file_and_evaluate(client):
    agent_id = client.post(
        "/api/v1/agents", json={"name": "Evaluator"}, cookies=_cookies()
    ).json()["id"]
    r = client.post("/api/v1/knowledge/ingest-file", data={"doc_id": "rfp1"},
                    files={"file": ("rfp.txt", ISO, "text/plain")}, cookies=_cookies())
    assert r.status_code == 200 and r.json()["chunks"] >= 1
    assert client.get("/api/v1/knowledge/rfp-criteria", cookies=_cookies()).json()["criteria"]
    ev = client.post("/api/v1/knowledge/evaluate",
                     json={"doc_id": "rfp1", "criterion": "Are certifications evidenced?",
                           "topic": "rfp", "agent_id": agent_id}, cookies=_cookies()).json()
    assert "ISO 9001" in ev["answer"] and "decision" in ev


def test_non_dev_voice_fails_closed_without_supported_gateway(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", Environment.preprod)
    app = create_app()
    assert isinstance(app.state.voice.speech, UnavailableSpeechGateway)


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
                     files={"file": ("q3.xlsx", _wb(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, cookies=_cookies())
    assert up.json()["records"] == 1
    a = client.post("/api/v1/excel/analytics", json={"rows": [["region", "revenue"], ["EMEA", 120000], ["APAC", 90000]]}, cookies=_cookies()).json()
    assert a["columns"]["revenue"]["sum"] == 210000
    rep = client.post("/api/v1/excel/report", json={"source": "q3", "analytics": a, "fmt": "xlsx"}, cookies=_cookies()).json()
    assert rep["key"].endswith(".xlsx")


def test_signal_buckets_recs_export(client):
    assert client.get("/api/v1/signal/buckets/s1", cookies=_cookies()).status_code == 200
    assert client.get("/api/v1/signal/recommendations/s1", cookies=_cookies()).json() == []
    assert client.post("/api/v1/signal/export/s1", cookies=_cookies()).json()["url"].endswith(".pdf")


def test_voice_web_call_config(client):
    cfg = client.get("/api/v1/voice/web-call-config", cookies=_cookies()).json()
    assert cfg["provider"] == "bedrock-nova-sonic" and "key" not in str(cfg).lower()


def test_signal_endpoints_503_instead_of_serving_stub_data(client, monkeypatch):
    """H3: with no SIGNAL_ENGINE_URL the engine is a stub returning score 0 / empty buckets / a
    non-existent export path. Answering 200 with that is indistinguishable from a real result."""
    from app.core.config import Environment, get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "environment", Environment.preprod)
    monkeypatch.setattr(settings, "signal_engine_url", "")
    c = auth_cookies("sigco", "owner")
    r = client.post("/api/v1/signal/projects", json={"brand": "Acme", "domain": "acme.invalid"}, cookies=c)
    assert r.status_code == 503 and "not configured" in r.json()["detail"]


def test_voice_speak_rejects_invalid_base64_with_422_not_500(client):
    """H2: base64.b64decode was on the request path with no validation -> binascii.Error -> 500."""
    c = auth_cookies("voiceco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "W"}, cookies=c).json()
    r = client.post("/api/v1/voice/speak", cookies=c, json={
        "conversation_id": "c1", "audio_b64": "a", "agent_id": agent["id"]})
    assert r.status_code == 422 and "base64" in r.json()["detail"]


def test_generated_file_and_report_bodies_reject_malformed_specs(client):
    """M3: untyped dict bodies raised TypeError/AttributeError deep in rendering -> unhandled 500."""
    c = auth_cookies("specco", "owner")
    assert client.post("/api/v1/chat/files", cookies=c, json={
        "fmt": "pdf", "filename": "x", "spec": {"paragraphs": [1]}}).status_code == 422
    assert client.post("/api/v1/chat/files", cookies=c, json={
        "fmt": "docx", "filename": "x", "spec": {"paragraphs": 5}}).status_code == 422
    assert client.post("/api/v1/excel/report", cookies=c, json={
        "source": "a", "analytics": {"columns": "x"}}).status_code == 422
