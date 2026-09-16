"""Background generation of ALL tender artifacts on upload.

Uploading an RFP kicks off a background job (eager/inline in tests) that produces + persists
Requirements, Sections, the Tender Brief, the Compliance checklist and per-section draft answers,
exposing a pollable per-artifact gen_status. See app.modules.rfp.generation / app.tasks.jobs.
"""
import asyncio
import io
import json

from app.modules.agentcore.models import AgentResult, Critique, Decision
from app.modules.agents.service import Agent
from app.modules.ai.gateway import LLMResponse
from app.modules.rfp import generation
from app.modules.rfp.extraction import ExtractionError
from app.modules.rfp.service import PackAnswerService, RequirementService, RfpPackService
from app.modules.rfp.tree import PackTreeService

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

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
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


def _patch_worker(monkeypatch, builder):
    async def resolve(**_kwargs):
        async def recheck():
            return None
        return await builder(), recheck
    monkeypatch.setattr(generation, "resolve_available_worker", resolve)


def _patch(monkeypatch, *, stub=False):
    monkeypatch.setattr("app.modules.rfp.generation.document_provider", lambda **_kw: _RoutingProvider())
    _patch_worker(monkeypatch, _worker_factory(stub=stub))


def _pack(client, tenant):
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="w1", tenant=tenant, name="Worker")))
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
    assert status["drafts"] == {"state": "ready", "done": 1, "total": 1, "failed": 0, "failed_ids": []}
    assert status["error"] is None
    assert status["errors"] == {}


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


def test_retry_drafting_clears_the_stale_failure_banner_state(client, monkeypatch):
    """IDG-1010, reported live: after the retry finally drafted everything, the failure banner
    stayed on screen. The banner reads gen_status.drafts, and only the background job ever wrote
    that block, so a successful inline retry left the original failure snapshot behind. Observed
    on preprod: all 48 questions drafted, status still {"state": "error", "done": 6, "total": 48}.

    This walks the whole reported path: an outage leaves drafts in "error" with nothing drafted,
    the retry then drafts everything, and the status has to say so."""
    _patch(monkeypatch, stub=True)  # provider outage on upload
    c, pid = _pack(client, "genretrybanner")
    _upload(client, c, pid)

    stale = client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()
    assert stale["drafts"]["state"] == "error"
    assert stale["errors"]["drafts"] == "answer generation is temporarily unavailable"

    # Provider recovers, reviewer clicks "Retry drafting" (only_missing=true is what it calls).
    monkeypatch.setattr("app.modules.rfp.router.resolve_tenant_worker",
                        _http_worker(answer="Recovered draft"))
    assert client.post(f"/api/v1/rfp/packs/{pid}/generate?only_missing=true",
                       cookies=c).status_code == 200

    status = client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()
    assert status["drafts"]["state"] == "ready"
    assert status["drafts"]["done"] == status["drafts"]["total"] > 0
    assert status["drafts"]["failed"] == 0 and status["drafts"]["failed_ids"] == []
    # The outage text must go with it, or the stage reads healthy next to a stale error.
    assert status["errors"] == {} and status["error"] is None


def test_regenerating_the_last_missing_question_also_clears_the_banner(client, monkeypatch):
    """Same invariant on the single-question path, which is the workaround a reviewer reaches for
    when the batch retry is the thing that is broken. It cleared the answer but not the status."""
    _patch(monkeypatch, stub=True)
    c, pid = _pack(client, "genregenbanner")
    _upload(client, c, pid)
    assert client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()["drafts"]["state"] == "error"

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    qid = tree[0]["questions"][0]["id"]
    monkeypatch.setattr("app.modules.rfp.router.resolve_tenant_worker",
                        _http_worker(answer="Recovered draft"))
    assert client.post(f"/api/v1/rfp/packs/{pid}/questions/{qid}/generate",
                       cookies=c).status_code == 200

    status = client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()
    assert status["drafts"]["state"] == "ready"
    assert status["errors"] == {}


def _http_worker(*, answer="Grounded AI draft", stub=False):
    """Worker resolver for the ROUTER path (the inline endpoints), as opposed to `_patch_worker`
    above which patches the background job's resolver."""
    async def resolve(*_a, **_kw):
        class _W:
            async def answer(self, rid, text, **__):
                return AgentResult(requirement_id=rid, answer=answer,
                                   critique=Critique(grounding=0.9), decision=Decision.auto_accept,
                                   citations=["doc:iso"], stub=stub)

        async def recheck():
            return None
        return _W(), recheck
    return resolve


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


# --- service-level run_generation: drafts isolation / resumability / per-stage errors ---
async def _make_pack(document_text="tender doc"):
    packs, reqs = RfpPackService(), RequirementService()
    answers, tree = PackAnswerService(), PackTreeService()
    pack = await packs.create("t", "w1", "Tender")
    await packs.set_document_text("t", pack.id, document_text)
    return packs, reqs, answers, tree, pack


async def _pack_with_stale_drafts_status(*, drafted: int, missing: int):
    """A pack carrying the failure snapshot the background job left behind, plus a question tree
    that has since moved on: `drafted` questions answered, `missing` still blank."""
    packs, _reqs, _answers, tree, pack = await _make_pack()
    section = await tree.add_section("t", pack.id, code="A", name="Intro")
    for i in range(drafted):
        q = await tree.add_question("t", section.id, text=f"answered-{i}")
        await tree.apply_generation("t", q.id, ai_answer="draft", ai_sources=["doc:iso"],
                                    confidence=0.9, decision="auto_accept", kb_gap=False)
    for i in range(missing):
        await tree.add_question("t", section.id, text=f"blank-{i}")
    await packs.set_gen_status("t", pack.id, {
        "requirements": "ready", "sections": "ready", "brief": "ready", "compliance": "ready",
        "drafts": {"state": "error", "done": 0, "total": 99, "failed": 0, "failed_ids": []},
        "error": "answer generation is temporarily unavailable",
        "errors": {"drafts": "answer generation is temporarily unavailable"},
    })
    return packs, tree, pack


async def test_refresh_drafts_status_reports_ready_once_nothing_is_missing():
    packs, tree, pack = await _pack_with_stale_drafts_status(drafted=3, missing=0)

    saved = await generation.refresh_drafts_status(
        tenant="t", pack_id=pack.id, packs=packs, tree=tree)

    assert saved["drafts"] == {"state": "ready", "done": 3, "total": 3,
                               "failed": 0, "failed_ids": []}
    assert saved["error"] is None and saved["errors"] == {}
    assert (await packs.get("t", pack.id)).gen_status["drafts"]["state"] == "ready"


async def test_refresh_drafts_status_reports_partial_while_some_are_still_blank():
    packs, tree, pack = await _pack_with_stale_drafts_status(drafted=2, missing=1)

    saved = await generation.refresh_drafts_status(
        tenant="t", pack_id=pack.id, packs=packs, tree=tree)

    assert saved["drafts"]["state"] == "partial"
    assert saved["drafts"]["done"] == 2 and saved["drafts"]["total"] == 3
    assert saved["drafts"]["failed"] == 1 and len(saved["drafts"]["failed_ids"]) == 1
    # Still genuinely failing, so the outage text stays: the banner is supposed to be up.
    assert saved["errors"]["drafts"] == "answer generation is temporarily unavailable"


async def test_refresh_drafts_status_reports_error_when_nothing_is_drafted_at_all():
    """"Drafting failed" rather than the softer "Some answers couldn't be drafted": the banner
    renders two different headlines off this distinction."""
    packs, tree, pack = await _pack_with_stale_drafts_status(drafted=0, missing=2)

    saved = await generation.refresh_drafts_status(
        tenant="t", pack_id=pack.id, packs=packs, tree=tree)

    assert saved["drafts"]["state"] == "error"
    assert saved["drafts"]["done"] == 0 and saved["drafts"]["failed"] == 2


async def test_refresh_drafts_status_leaves_a_pack_with_no_gen_status_alone():
    """Packs from before the background job carry no gen_status, and the frontend has a
    documented fallback that lands them on Review when their sections exist. Writing a status for
    them would push them back a step, so this must be a no-op."""
    packs, _reqs, _answers, tree, pack = await _make_pack()
    section = await tree.add_section("t", pack.id, code="A", name="Intro")
    await tree.add_question("t", section.id, text="Q1")

    assert await generation.refresh_drafts_status(
        tenant="t", pack_id=pack.id, packs=packs, tree=tree) is None
    assert not (await packs.get("t", pack.id)).gen_status


def _stub_supporting_stages(monkeypatch):
    """Make the provider + brief + compliance stages trivially succeed so a run_generation test can
    focus on the drafts stage."""
    monkeypatch.setattr(generation, "document_provider", lambda **_kw: object())
    monkeypatch.setattr(generation, "extract_brief", lambda *_a, **_kw: {"summary": "s"})
    monkeypatch.setattr(generation, "extract_compliance", lambda *_a, **_kw: [])


def _draft_worker(*, fail_ids=(), record=None):
    """A fake worker whose answer() drafts a grounded result, but RAISES for any req_id in
    `fail_ids` (to exercise per-item isolation) and appends each req_id it saw to `record`."""
    async def _build(*_a, **_kw):
        class _W:
            async def answer(self, rid, text, **__):
                if record is not None:
                    record.append(rid)
                if rid in fail_ids:
                    raise RuntimeError(f"draft failed for {rid}")
                return AgentResult(requirement_id=rid, answer="draft",
                                   critique=Critique(grounding=0.9), decision=Decision.auto_accept,
                                   citations=["doc:iso"], stub=False)
        return _W()
    return _build


def _coarse(*codes):
    return [{"id": c, "title": f"S{c}", "classification": "KB",
             "requirement": f"describe {c}", "subsections": []} for c in codes]


async def test_drafts_loop_isolates_a_failing_question_and_marks_partial(monkeypatch):
    """C1: one question raising must NOT abort the rest -- the others still draft, the failure is
    counted (failed/failed_ids) and the stage ends "partial", not "error"."""
    packs, reqs, answers, tree, pack = await _make_pack()
    _stub_supporting_stages(monkeypatch)

    async def _extract(_text, **_kwargs):
        return _coarse("A1", "A2", "A3")
    monkeypatch.setattr(generation, "extract_requirements_chunked", _extract)
    _patch_worker(monkeypatch, _draft_worker(fail_ids={"A2"}))

    status = await generation.run_generation(
        tenant="t", pack_id=pack.id, agent_id=None, packs=packs, reqs=reqs, answers=answers,
        tree=tree, knowledge=None, agents=None)

    assert status["drafts"]["state"] == "partial"
    assert status["drafts"]["total"] == 3
    assert status["drafts"]["done"] == 2
    assert status["drafts"]["failed"] == 1
    assert status["drafts"]["failed_ids"] == ["A2"]
    qs = {q.req_id: q for q in await tree.questions.list("t", pack.id)}
    assert qs["A1"].ai_answer == "draft" and qs["A3"].ai_answer == "draft"
    assert qs["A2"].ai_answer == ""  # the failing question was left un-drafted, not persisted
    assert status["errors"] == {}  # a per-item failure is isolated, not a whole-stage error


async def test_drafts_loop_resumes_and_skips_already_drafted(monkeypatch):
    """C1 resumability: a question that ALREADY has a draft is skipped on a re-run, so an arq retry
    (worker restart mid-run) resumes the not-yet-drafted work rather than re-drafting from zero."""
    packs, reqs, answers, tree, pack = await _make_pack()
    _stub_supporting_stages(monkeypatch)

    # a prior run already built the tree and drafted A1
    await tree.populate_from_extraction("t", pack.id, _coarse("A1", "A2"))
    a1_q = next(q for q in await tree.questions.list("t", pack.id) if q.req_id == "A1")
    await tree.apply_generation("t", a1_q.id, ai_answer="prior draft", ai_sources=[],
                                confidence=0.5, decision="auto_accept", kb_gap=False)

    # on the retry extraction transiently fails, so the existing tree is NOT wiped; drafts resume
    async def _boom(_text, **_kwargs):
        raise ExtractionError("transient extraction outage")
    monkeypatch.setattr(generation, "extract_requirements_chunked", _boom)
    seen: list[str] = []
    _patch_worker(monkeypatch, _draft_worker(record=seen))

    status = await generation.run_generation(
        tenant="t", pack_id=pack.id, agent_id=None, packs=packs, reqs=reqs, answers=answers,
        tree=tree, knowledge=None, agents=None)

    assert seen == ["A2"]  # only the not-yet-drafted question was (re)drafted, no duplicate work
    assert status["drafts"] == {"state": "ready", "done": 2, "total": 2,
                                "failed": 0, "failed_ids": []}
    qs = {q.req_id: q for q in await tree.questions.list("t", pack.id)}
    assert qs["A1"].ai_answer == "prior draft"  # untouched
    assert qs["A2"].ai_answer == "draft"


async def test_drafts_stub_fallback_still_fails_closed(monkeypatch):
    """C1: a genuine provider outage (StubProviderUnavailable) still fails closed -- state "error",
    nothing persisted -- rather than being swallowed as a per-item failure."""
    packs, reqs, answers, tree, pack = await _make_pack()
    _stub_supporting_stages(monkeypatch)

    async def _extract(_text, **_kwargs):
        return _coarse("A1", "A2")
    monkeypatch.setattr(generation, "extract_requirements_chunked", _extract)

    async def _stub_build(*_a, **_kw):
        class _W:
            async def answer(self, rid, text, **__):
                return AgentResult(requirement_id=rid, answer="echo", critique=Critique(grounding=0.0),
                                   decision=Decision.human_review, citations=[], stub=True)
        return _W()
    _patch_worker(monkeypatch, _stub_build)

    status = await generation.run_generation(
        tenant="t", pack_id=pack.id, agent_id=None, packs=packs, reqs=reqs, answers=answers,
        tree=tree, knowledge=None, agents=None)

    assert status["drafts"]["state"] == "error"
    assert status["errors"]["drafts"] == "answer generation is temporarily unavailable"
    assert all(q.ai_answer == "" for q in await tree.questions.list("t", pack.id))


async def test_per_stage_errors_are_attributed_not_clobbered(monkeypatch):
    """M3: each failing stage records its own message under errors[stage] so a poller can tell WHICH
    stage failed, instead of one shared `error` field clobbering the others."""
    packs, reqs, answers, tree, pack = await _make_pack()
    monkeypatch.setattr(generation, "document_provider", lambda **_kw: object())

    async def _req_boom(_text, **_kwargs):
        raise ExtractionError("req boom")
    monkeypatch.setattr(generation, "extract_requirements_chunked", _req_boom)
    monkeypatch.setattr(generation, "extract_brief", lambda *_a, **_kw: {"summary": "s"})

    def _comp_boom(*_a, **_kw):
        raise RuntimeError("comp boom")
    monkeypatch.setattr(generation, "extract_compliance", _comp_boom)
    _patch_worker(monkeypatch, _draft_worker())

    status = await generation.run_generation(
        tenant="t", pack_id=pack.id, agent_id=None, packs=packs, reqs=reqs, answers=answers,
        tree=tree, knowledge=None, agents=None)

    assert status["requirements"] == "error" and status["compliance"] == "error"
    assert status["brief"] == "ready"
    assert "req boom" in status["errors"]["requirements"]
    assert "comp boom" in status["errors"]["compliance"]
    assert status["error"] is not None  # latest error kept for back-compat


def test_consolidate_dedupes_colliding_codes_across_chunks():
    """M1: two chunks that each returned "B1" with a different title survive the title-keyed merge,
    so _consolidate must re-uniquify their codes (and sub-section req_ids)."""
    out = generation._consolidate([
        {"id": "B1", "title": "From chunk A", "classification": "KB", "requirement": "a",
         "subsections": [{"id": "B1.1", "title": "sa", "classification": "KB", "requirement": "x"}]},
        {"id": "B1", "title": "From chunk B", "classification": "KB", "requirement": "b",
         "subsections": [{"id": "B1.1", "title": "sb", "classification": "KB", "requirement": "y"}]},
    ])
    assert [o["id"] for o in out] == ["B1", "B1-2"]
    assert out[1]["subsections"][0]["id"] == "B1-2.1"
