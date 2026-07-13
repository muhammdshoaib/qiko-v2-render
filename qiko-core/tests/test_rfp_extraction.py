import io
import json

import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.rfp.extraction import ExtractionError, extract_requirements

from tests.helpers import auth_cookies

SAMPLE_JSON = json.dumps([
    {"id": "A1", "title": "Company Profile", "classification": "KB",
     "requirement": "Describe your company's experience in security services."},
    {"id": "A2", "title": "Pricing", "classification": "MANUAL",
     "requirement": "Complete the pricing schedule in the prescribed format."},
])


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2):
        return LLMResponse(text=self.text)


def test_extract_requirements_parses_clean_json():
    items = extract_requirements("some tender text", _CannedProvider(SAMPLE_JSON))
    assert len(items) == 2
    assert items[0] == {"id": "A1", "title": "Company Profile", "classification": "KB",
                        "requirement": "Describe your company's experience in security services."}
    assert items[1]["classification"] == "MANUAL"


def test_extract_requirements_handles_markdown_fenced_json():
    fenced = f"Here you go:\n```json\n{SAMPLE_JSON}\n```"
    items = extract_requirements("tender text", _CannedProvider(fenced))
    assert len(items) == 2


def test_extract_requirements_defaults_unknown_classification_to_kb():
    raw = json.dumps([{"id": "B1", "title": "Something", "classification": "WEIRD",
                       "requirement": "Do the thing."}])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert items[0]["classification"] == "KB"


def test_extract_requirements_rejects_non_json():
    with pytest.raises(ExtractionError):
        extract_requirements("tender text", _CannedProvider("not json at all"))


def test_extract_requirements_rejects_empty_array():
    with pytest.raises(ExtractionError):
        extract_requirements("tender text", _CannedProvider("[]"))


# --- API-level: full upload -> extract -> list round trip ---
def test_rfp_extract_endpoint_round_trip(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(SAMPLE_JSON))

    c = auth_cookies("extractco", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender X"}, cookies=c).json()

    upload = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                         files={"file": ("tender.txt", io.BytesIO(b"tender document text"), "text/plain")})
    assert upload.status_code == 200
    extracted = upload.json()
    assert len(extracted) == 2
    assert extracted[0]["req_id"] == "A1"

    listed = client.get(f"/api/v1/rfp/packs/{pack['id']}/requirements", cookies=c).json()
    assert len(listed) == 2


def test_rfp_extract_rejects_unsupported_file_type(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(SAMPLE_JSON))
    c = auth_cookies("extractco2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender Y"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                    files={"file": ("tender.exe", io.BytesIO(b"binary"), "application/octet-stream")})
    assert r.status_code == 422


def test_rfp_extract_404_for_missing_pack(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(SAMPLE_JSON))
    c = auth_cookies("extractco3", "owner")
    r = client.post("/api/v1/rfp/packs/missing/extract", cookies=c,
                    files={"file": ("tender.txt", io.BytesIO(b"text"), "text/plain")})
    assert r.status_code == 404
