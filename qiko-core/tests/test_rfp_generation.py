"""Background generation of ALL tender artifacts on upload.

Uploading an RFP kicks off a background job (eager/inline in tests) that produces + persists
Requirements, Sections, the Tender Brief, the Compliance checklist and per-section draft answers,
exposing a pollable per-artifact gen_status. See app.modules.rfp.generation / app.tasks.jobs.
"""
import io
import json

from app.modules.agentcore.models import AgentResult, Critique, Decision
from app.modules.ai.gateway import LLMResponse

from tests.helpers import auth_cookies

REQ_JSON = json.dumps([
    {"id": "A1", "title": "Company Profile", "classification": "KB",
     "requirement": "Describe your experience in ISO security services."},
])
BRIEF_JSON = json.dumps({
    "summary": "A tender for managed security services.",
    "scope": "Managed security services.",
    "submission_format": "Sealed electronic submission.",
    "key_dates": ["Deadline: 2026-08-01"],
    "success_criteria": ["Lowest compliant bid"],
    "gaps_and_risks": ["Tight timeline"],
})
COMPLIANCE_JSON = json.dumps([
    {"requirement": "Signed ISO security services declaration", "category": "Legal",
     "mandatory": True, "owner": "Human", "note": "Requires wet signature"},
])


class _RoutingProvider:
    """One provider that answers extraction / brief / compliance differently, dispatching on the
    system prompt each pipeline uses (the background job builds all three via get_provider)."""

    def generate(self, prompt, *, system=None, temperature=0.2):
        s = (system or "").lower()
        if "compliance analyst" in s:
            return LLMResponse(text=COMPLIANCE_JSON)
        if "bid manager" in s:
            return LLMResponse(text=BRIEF_JSON)
        return LLMResponse(text=REQ_JSON)


def _worker_factory(*, answer="Grounded AI draft", stub=False):
    async def _build(*_a, **_kw):
        class _W:
            async def answer(self, rid, text, **__):
                return AgentResult(requirement_id=rid, answer=answer,
                                   critique=Critique(grounding=0.9), decision=Decision.auto_accept,
                                   citations=["doc:iso"], stub=stub)
        return _W()
    return _build


def _patch(monkeypatch, *, stub=False):
    monkeypatch.setattr("app.modules.rfp.generation.get_provider", lambda **_kw: _RoutingProvider())
    monkeypatch.setattr("app.modules.rfp.generation.assemble_worker", _worker_factory(stub=stub))


def _pack(client, tenant):
    c = auth_cookies(tenant, "owner")
    pid = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender"}, cookies=c).json()["id"]
    return c, pid


def _upload(client, c, pid, body=b"tender document about ISO security services"):
    return client.post(f"/api/v1/rfp/packs/{pid}/extract", cookies=c,
                       files={"file": ("t.txt", io.BytesIO(body), "text/plain")})


def test_upload_returns_processing_and_enqueues(client, monkeypatch):
    _patch(monkeypatch)
    c, pid = _pack(client, "genupload")
    r = _upload(client, c, pid)
    assert r.status_code == 202
    assert r.json() == {"status": "processing", "pack_id": pid}


def test_job_populates_every_artifact_and_marks_status_ready(client, monkeypatch):
    _patch(monkeypatch)
    c, pid = _pack(client, "genfull")
    _upload(client, c, pid)  # eager backend runs the whole job inline

    # requirements + sections
    reqs = client.get(f"/api/v1/rfp/packs/{pid}/requirements", cookies=c).json()
    assert [r["req_id"] for r in reqs] == ["A1"]
    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    assert len(tree) == 1 and tree[0]["questions"][0]["ai_answer"] == "Grounded AI draft"

    # brief + compliance persisted and readable via the new GET endpoints
    brief = client.get(f"/api/v1/rfp/packs/{pid}/brief", cookies=c).json()
    assert brief["summary"] == "A tender for managed security services."
    compliance = client.get(f"/api/v1/rfp/packs/{pid}/compliance", cookies=c).json()
    assert compliance[0]["category"] == "Legal"

    # per-artifact status all ready, drafts fully done
    status = client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()
    assert status["requirements"] == "ready"
    assert status["sections"] == "ready"
    assert status["brief"] == "ready"
    assert status["compliance"] == "ready"
    assert status["drafts"] == {"state": "ready", "done": 1, "total": 1}
    assert status["error"] is None


def test_stub_guard_stops_drafts_without_persisting(client, monkeypatch):
    # A StubProvider fallback for the drafts stage must not be persisted onto the question.
    _patch(monkeypatch, stub=True)
    c, pid = _pack(client, "genstub")
    _upload(client, c, pid)

    status = client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()
    # extraction/brief/compliance still succeeded; only drafts failed closed
    assert status["requirements"] == "ready" and status["brief"] == "ready"
    assert status["drafts"]["state"] == "error"

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    assert tree[0]["questions"][0]["ai_answer"] == ""  # nothing written from the stub


def test_status_brief_compliance_empty_before_any_job(client, monkeypatch):
    _patch(monkeypatch)
    c, pid = _pack(client, "genempty")  # created but nothing uploaded yet
    assert client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json() == {}
    assert client.get(f"/api/v1/rfp/packs/{pid}/brief", cookies=c).json() is None
    assert client.get(f"/api/v1/rfp/packs/{pid}/compliance", cookies=c).json() == []


def test_read_endpoints_are_tenant_scoped(client, monkeypatch):
    _patch(monkeypatch)
    c, pid = _pack(client, "gentenantA")
    _upload(client, c, pid)

    other = auth_cookies("gentenantB", "owner")  # a different tenant must not see this pack
    assert client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=other).status_code == 404
    assert client.get(f"/api/v1/rfp/packs/{pid}/brief", cookies=other).status_code == 404
    assert client.get(f"/api/v1/rfp/packs/{pid}/compliance", cookies=other).status_code == 404


def test_read_endpoints_404_for_missing_pack(client):
    c = auth_cookies("genmissing", "owner")
    assert client.get("/api/v1/rfp/packs/nope/status", cookies=c).status_code == 404
    assert client.get("/api/v1/rfp/packs/nope/brief", cookies=c).status_code == 404
    assert client.get("/api/v1/rfp/packs/nope/compliance", cookies=c).status_code == 404
