import io
import json

import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.rfp.brief import BriefError, extract_brief
from app.modules.rfp.compliance import ComplianceError, extract_compliance

from tests.helpers import auth_cookies

TENDER_TEXT = "This tender requires bidders to submit a signed declaration confirming ISO 27001 compliance."

COMPLIANCE_JSON = json.dumps([
    {"requirement": "Signed declaration confirming ISO 27001 compliance", "category": "Legal",
     "mandatory": True, "owner": "Human", "note": "Requires wet signature"},
])

BRIEF_JSON = json.dumps({
    "summary": "A short tender for IT security services.",
    "scope": "Managed security services.",
    "submission_format": "Sealed electronic submission.",
    "key_dates": ["Deadline: 2026-08-01"],
    "success_criteria": ["Lowest compliant bid"],
    "gaps_and_risks": ["Tight timeline"],
})


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2):
        return LLMResponse(text=self.text)


def test_extract_compliance_grounds_and_defaults_owner():
    items = extract_compliance(TENDER_TEXT, _CannedProvider(COMPLIANCE_JSON))
    assert len(items) == 1
    assert items[0]["category"] == "Legal"
    assert items[0]["owner"] == "Human"
    assert items[0]["grounded"] is True  # shares real vocabulary with the source text


def test_extract_compliance_flags_ungrounded_item():
    fabricated = json.dumps([{"requirement": "Provide a notarized alien registration waiver",
                              "category": "Legal", "mandatory": True, "owner": "Human"}])
    items = extract_compliance(TENDER_TEXT, _CannedProvider(fabricated))
    assert items[0]["grounded"] is False


def test_extract_compliance_rejects_empty():
    with pytest.raises(ComplianceError):
        extract_compliance(TENDER_TEXT, _CannedProvider("[]"))


def test_extract_brief_parses_all_fields():
    brief = extract_brief(TENDER_TEXT, _CannedProvider(BRIEF_JSON))
    assert brief["summary"] == "A short tender for IT security services."
    assert brief["key_dates"] == ["Deadline: 2026-08-01"]


def test_extract_brief_rejects_missing_summary():
    with pytest.raises(BriefError):
        extract_brief(TENDER_TEXT, _CannedProvider(json.dumps({"summary": ""})))


# --- API-level ---
def test_compliance_and_brief_endpoints(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(COMPLIANCE_JSON))
    c = auth_cookies("compbrief", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender Z"}, cookies=c).json()

    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/compliance", cookies=c,
                    files={"file": ("t.txt", io.BytesIO(TENDER_TEXT.encode()), "text/plain")})
    assert r.status_code == 200 and r.json()[0]["category"] == "Legal"

    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(BRIEF_JSON))
    r2 = client.post(f"/api/v1/rfp/packs/{pack['id']}/brief", cookies=c,
                     files={"file": ("t.txt", io.BytesIO(TENDER_TEXT.encode()), "text/plain")})
    assert r2.status_code == 200 and r2.json()["summary"]


def test_compliance_404_for_missing_pack(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(COMPLIANCE_JSON))
    c = auth_cookies("compbrief2", "owner")
    r = client.post("/api/v1/rfp/packs/missing/compliance", cookies=c,
                    files={"file": ("t.txt", io.BytesIO(b"text"), "text/plain")})
    assert r.status_code == 404
