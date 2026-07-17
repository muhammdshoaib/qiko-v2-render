import io
import json

from app.modules.ai.gateway import LLMResponse
from app.modules.rfp.scoring import ScoringError, score_opportunity

from tests.helpers import auth_cookies

GOOD_JSON = json.dumps({
    "score": 82, "qualified": True,
    "rationale": "Strong fit: scope matches our services and the deadline is workable.",
    "criteria_results": [
        {"criterion": "Is the scope a match?", "met": True, "note": "Static security services, matches."},
        {"criterion": "Is the deadline realistic?", "met": True, "note": "6 weeks out."},
    ],
})


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text)


# --- pure function ---
def test_score_opportunity_parses_clean_json():
    result = score_opportunity("tender text", ["Is the scope a match?", "Is the deadline realistic?"], _CannedProvider(GOOD_JSON))
    assert result["score"] == 82
    assert result["qualified"] is True
    assert len(result["criteria_results"]) == 2
    assert result["criteria_results"][0]["met"] is True


def test_score_opportunity_falls_back_to_default_criteria_when_none_configured():
    result = score_opportunity("tender text", [], _CannedProvider(GOOD_JSON))
    assert result["score"] == 82  # still scores fine -- the fallback criteria are used server-side


def test_score_opportunity_clamps_out_of_range_score():
    raw = json.dumps({"score": 500, "qualified": True, "rationale": "x", "criteria_results": []})
    result = score_opportunity("t", ["c1"], _CannedProvider(raw))
    assert result["score"] == 100


def test_score_opportunity_rejects_non_json():
    try:
        score_opportunity("t", ["c1"], _CannedProvider("not json"))
        raise AssertionError("expected ScoringError")
    except ScoringError:
        pass


def test_score_opportunity_rejects_missing_rationale():
    raw = json.dumps({"score": 50, "qualified": False, "criteria_results": []})
    try:
        score_opportunity("t", ["c1"], _CannedProvider(raw))
        raise AssertionError("expected ScoringError")
    except ScoringError:
        pass


class _FlakyProvider:
    """Returns each queued response in turn (last one sticks) so we can test retry-then-succeed."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        text = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return LLMResponse(text=text)


def test_score_opportunity_retries_then_succeeds_on_bad_json():
    p = _FlakyProvider("not json at all", GOOD_JSON)
    result = score_opportunity("t", ["c1"], p)
    assert result["score"] == 82
    assert p.calls == 2  # first attempt failed to parse, retried and succeeded


def test_score_opportunity_drops_malformed_criterion_keeps_valid():
    raw = json.dumps({
        "score": 60, "qualified": True, "rationale": "ok",
        "criteria_results": [
            {"criterion": "Valid one", "met": True, "note": "n"},
            "not an object",
            {"criterion": "Another valid", "met": False, "note": ""},
        ],
    })
    result = score_opportunity("t", ["c1"], _CannedProvider(raw))
    assert len(result["criteria_results"]) == 2  # the string entry is dropped, the two dicts survive


# --- API-level ---
def test_score_endpoint_uses_the_pack_worker_configured_criteria(client, monkeypatch):
    extract_json = json.dumps([{"id": "A1", "title": "Scope", "classification": "KB", "requirement": "Describe scope."}])

    class _RespondingByPrompt:
        def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
            if "CRITERIA:" in prompt:
                return LLMResponse(text=GOOD_JSON)
            return LLMResponse(text=extract_json)

    async def _stub_worker(**_kw):
        from app.modules.agentcore.models import AgentResult, Critique, Decision

        class _W:
            async def answer(self, rid, text, **__):
                return AgentResult(requirement_id=rid, answer="", critique=Critique(grounding=0.0),
                                   decision=Decision.human_review, citations=[], stub=True)
        return _W()

    # /score reads router.get_provider; the background /extract job reads generation.get_provider.
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _RespondingByPrompt())
    monkeypatch.setattr("app.modules.rfp.generation.get_provider", lambda **_kw: _RespondingByPrompt())
    monkeypatch.setattr("app.modules.rfp.generation.assemble_worker", _stub_worker)
    c = auth_cookies("scoreco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "IDG Sales"}, cookies=c).json()
    client.put(f"/api/v1/agents/{agent['id']}/config", cookies=c,
              json={"patch": {"opportunity_criteria": ["Is the scope a match?", "Is the deadline realistic?"]}})
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": agent["id"], "title": "T"}, cookies=c).json()
    extract_resp = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                               files={"file": ("t.txt", io.BytesIO(b"Static security services tender, due in 6 weeks."), "text/plain")})
    assert extract_resp.status_code == 202

    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/score", cookies=c)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 82 and body["qualified"] is True
    assert len(body["criteria_results"]) == 2


def test_score_endpoint_requires_a_document_on_file(client):
    c = auth_cookies("scoreco2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/score", cookies=c)
    assert r.status_code == 422


def test_score_endpoint_404_for_missing_pack(client):
    c = auth_cookies("scoreco3", "owner")
    r = client.post("/api/v1/rfp/packs/missing/score", cookies=c)
    assert r.status_code == 404


def test_score_endpoint_requires_editor_role(client):
    c = auth_cookies("scoreco4", "viewer")
    r = client.post("/api/v1/rfp/packs/x/score", cookies=c)
    assert r.status_code == 403
