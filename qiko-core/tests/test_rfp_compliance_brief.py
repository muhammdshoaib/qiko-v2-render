import io
import json

import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.rfp.brief import BriefError, extract_brief
from app.modules.rfp.compliance import ComplianceError, extract_compliance

from tests.helpers import auth_cookies, autoseed_rfp_pack_workers

TENDER_TEXT = "This tender requires bidders to submit a signed declaration confirming ISO 27001 compliance."


@pytest.fixture(autouse=True)
def _seed_pack_workers(client, monkeypatch):
    autoseed_rfp_pack_workers(client, monkeypatch)

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

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text)


class _FlakyProvider:
    """Returns a different response per call so retry behaviour can be exercised: the first call
    gets `responses[0]`, the second `responses[1]`, etc. (last is repeated if over-called)."""
    def __init__(self, *responses: str):
        self.responses = responses
        self.calls = 0

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        text = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return LLMResponse(text=text)


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


def test_extract_compliance_output_shape_unchanged():
    """The per-item dict keeps EXACTLY the keys the endpoint persists and the FE `ComplianceItem`
    type consumes, plus the derived `grounded` flag -- byte-for-byte with the pre-hardening shape."""
    items = extract_compliance(TENDER_TEXT, _CannedProvider(COMPLIANCE_JSON))
    assert set(items[0]) == {"requirement", "category", "mandatory", "owner", "note", "grounded"}
    assert items[0]["mandatory"] is True and items[0]["note"] == "Requires wet signature"


def test_extract_compliance_normalises_category_and_owner():
    """Validators normalise an out-of-set category to "Format" and any non-"ai" owner to "Human"."""
    raw = json.dumps([{"requirement": "Submit a signed ISO 27001 declaration", "category": "Weird",
                       "mandatory": True, "owner": "robot", "note": ""}])
    items = extract_compliance(TENDER_TEXT, _CannedProvider(raw))
    assert items[0]["category"] == "Format" and items[0]["owner"] == "Human"


def test_extract_compliance_drops_malformed_items_keeps_valid():
    """A single malformed item (missing requirement / not an object) is dropped WITHOUT sinking the
    well-formed ones."""
    raw = json.dumps([
        {"requirement": "Signed ISO 27001 declaration", "category": "Legal", "owner": "Human"},
        {"category": "Legal", "owner": "Human"},          # no requirement -> dropped
        {"requirement": "", "category": "Legal"},         # empty requirement -> dropped
        "not an object",                                    # not a dict -> dropped
        {"requirement": "Provide the tender submission format", "category": "Format"},
    ])
    items = extract_compliance(TENDER_TEXT, _CannedProvider(raw))
    assert [i["requirement"] for i in items] == [
        "Signed ISO 27001 declaration", "Provide the tender submission format"]


def test_extract_compliance_retries_on_invalid_json_then_succeeds():
    """A first unparseable response is retried; the second, valid response is accepted."""
    provider = _FlakyProvider("not json", COMPLIANCE_JSON)
    items = extract_compliance(TENDER_TEXT, provider)
    assert provider.calls == 2 and len(items) == 1


def test_extract_compliance_retries_on_transient_provider_error():
    """L2: a RAW provider error (timeout/throttle), not a ComplianceError, on the first attempt is
    retried rather than propagating on attempt one."""
    class _TransientThenOk:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("provider read timeout")
            return LLMResponse(text=COMPLIANCE_JSON)

    provider = _TransientThenOk()
    items = extract_compliance(TENDER_TEXT, provider)
    assert provider.calls == 2 and len(items) == 1


def test_extract_compliance_raises_after_retries_exhausted():
    """Two unparseable responses in a row exhaust the retries and raise ComplianceError."""
    provider = _FlakyProvider("not json", "still not json")
    with pytest.raises(ComplianceError):
        extract_compliance(TENDER_TEXT, provider)
    assert provider.calls == 2


def test_extract_brief_parses_all_fields():
    brief = extract_brief(TENDER_TEXT, _CannedProvider(BRIEF_JSON))
    assert brief["summary"] == "A short tender for IT security services."
    assert brief["key_dates"] == ["Deadline: 2026-08-01"]


def test_extract_brief_output_shape_unchanged():
    """The brief keeps EXACTLY the keys the endpoint persists and the FE `TenderBrief` type consumes
    (three strings + three string arrays) -- byte-for-byte with the pre-hardening shape."""
    brief = extract_brief(TENDER_TEXT, _CannedProvider(BRIEF_JSON))
    assert set(brief) == {"summary", "scope", "submission_format", "key_dates",
                          "success_criteria", "gaps_and_risks"}
    assert brief["success_criteria"] == ["Lowest compliant bid"]
    assert brief["gaps_and_risks"] == ["Tight timeline"]


def test_extract_brief_handles_markdown_fenced_json():
    fenced = f"Here you go:\n```json\n{BRIEF_JSON}\n```"
    brief = extract_brief(TENDER_TEXT, _CannedProvider(fenced))
    assert brief["summary"] == "A short tender for IT security services."


def test_extract_brief_drops_malformed_list_entries_keeps_valid():
    """Missing lists default to []; a non-scalar (object/array) or empty entry in a list field is
    dropped while the valid string entries are kept."""
    raw = json.dumps({
        "summary": "A usable summary of the tender.",
        "key_dates": ["Deadline: 2026-08-01", "", {"label": "bad"}, None, "Q&A: 2026-07-01"],
        "success_criteria": ["Lowest compliant bid"],
        # scope, submission_format, gaps_and_risks missing entirely
    })
    brief = extract_brief(TENDER_TEXT, _CannedProvider(raw))
    assert brief["key_dates"] == ["Deadline: 2026-08-01", "Q&A: 2026-07-01"]
    assert brief["scope"] == "" and brief["submission_format"] == ""
    assert brief["gaps_and_risks"] == []


def test_extract_brief_retries_on_invalid_json_then_succeeds():
    """A first unparseable response is retried; the second, valid response is accepted."""
    provider = _FlakyProvider("not json", BRIEF_JSON)
    brief = extract_brief(TENDER_TEXT, provider)
    assert provider.calls == 2 and brief["summary"] == "A short tender for IT security services."


def test_extract_brief_retries_on_transient_provider_error():
    """L2: a RAW provider error (timeout/throttle), not a BriefError/ValidationError, on the first
    attempt is retried rather than propagating on attempt one."""
    class _TransientThenOk:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("provider read timeout")
            return LLMResponse(text=BRIEF_JSON)

    provider = _TransientThenOk()
    brief = extract_brief(TENDER_TEXT, provider)
    assert provider.calls == 2 and brief["summary"] == "A short tender for IT security services."


def test_extract_brief_raises_after_retries_exhausted():
    """Two invalid responses (no usable summary) in a row exhaust the retries and raise BriefError."""
    provider = _FlakyProvider(json.dumps({"summary": ""}), "not json at all")
    with pytest.raises(BriefError):
        extract_brief(TENDER_TEXT, provider)
    assert provider.calls == 2


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
