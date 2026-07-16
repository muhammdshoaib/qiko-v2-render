import io

import pytest

from app.modules.agentcore.models import AgentResult, Critique, Decision
from app.modules.rfp.service import PackRequirement
from app.modules.rfp.tree import PackQuestionNotFound, PackSectionNotFound, PackTreeService

from tests.helpers import auth_cookies


# --- service-level: CRUD, lock roll-up, overview, extraction wiring ---
async def test_section_and_question_crud():
    svc = PackTreeService()
    s = await svc.add_section("t", "p1", code="A1", name="Intro")
    assert s.status == "not_generated" and s.order_index == 0
    q = await svc.add_question("t", s.id, text="Describe X", word_limit=200)
    assert q.section_id == s.id and q.word_limit == 200

    edited = await svc.update_section("t", s.id, weighting="10%", assigned_reviewer_name="Sam")
    assert edited.weighting == "10%" and edited.assigned_reviewer_name == "Sam"
    eq = await svc.update_question("t", q.id, text="Describe Y")
    assert eq.text == "Describe Y"

    await svc.delete_question("t", q.id)
    with pytest.raises(PackQuestionNotFound):
        await svc.get_question("t", q.id)
    await svc.delete_section("t", s.id)
    with pytest.raises(PackSectionNotFound):
        await svc.get_section("t", s.id)


async def test_delete_section_cascades_questions():
    svc = PackTreeService()
    s = await svc.add_section("t", "p1", code="A1", name="Intro")
    await svc.add_question("t", s.id, text="Q1")
    await svc.add_question("t", s.id, text="Q2")
    await svc.delete_section("t", s.id)
    assert await svc.questions.list("t", "p1") == []


async def test_lock_rollup_and_all_sections_locked():
    svc = PackTreeService()
    s = await svc.add_section("t", "p1", code="A1", name="Intro")
    q1 = await svc.add_question("t", s.id, text="Q1")
    q2 = await svc.add_question("t", s.id, text="Q2")

    await svc.lock_question("t", q1.id)
    assert (await svc.get_section("t", s.id)).status != "locked"
    assert not await svc.all_sections_locked("t", "p1")

    await svc.lock_question("t", q2.id)
    assert (await svc.get_section("t", s.id)).status == "locked"
    assert await svc.all_sections_locked("t", "p1")

    # unlock rolls the section back off "locked"
    await svc.lock_question("t", q1.id, locked=False)
    assert (await svc.get_section("t", s.id)).status != "locked"
    assert not await svc.all_sections_locked("t", "p1")


async def test_lock_all_in_section():
    svc = PackTreeService()
    s = await svc.add_section("t", "p1", code="A1", name="Intro")
    await svc.add_question("t", s.id, text="Q1")
    await svc.add_question("t", s.id, text="Q2")
    rolled = await svc.lock_all_in_section("t", s.id)
    assert rolled.status == "locked"
    assert all(q.locked for q in await svc.questions.list_for_section("t", s.id))


async def test_extraction_wiring_groups_by_top_level_code():
    svc = PackTreeService()
    extracted = [
        {"id": "A1", "title": "Intro", "classification": "KB", "requirement": "Describe intro."},
        {"id": "B1.1", "title": "Org \u2014 Organogram", "classification": "KB", "requirement": "Org chart."},
        {"id": "B1.2", "title": "Org \u2014 Structure", "classification": "KB", "requirement": "Structure."},
        {"id": "C1", "title": "Pricing", "classification": "MANUAL", "requirement": "Complete pricing."},
    ]
    sections = await svc.populate_from_extraction("t", "p1", extracted)
    codes = {s.code: s for s in sections}
    assert set(codes) == {"A1", "B1", "C1"}
    # B1.1 + B1.2 collapse into one B1 section with two questions
    b1_qs = await svc.questions.list_for_section("t", codes["B1"].id)
    assert len(b1_qs) == 2 and {q.req_id for q in b1_qs} == {"B1.1", "B1.2"}
    assert codes["B1"].name == "Org"  # parent heading before the em-dash
    # a section whose items are all MANUAL/COMPLIANCE is flagged manual
    assert codes["C1"].manual is True and codes["A1"].manual is False


def _reqs(pack_id, *specs):
    """Flat PackRequirement rows as an old (pre-tree-feature) pack would already have stored."""
    return [PackRequirement(id=f"row{i}", tenant="t", pack_id=pack_id, req_id=rid, title=title,
                            classification=cls, requirement=req)
            for i, (rid, title, cls, req) in enumerate(specs)]


async def test_backfill_from_requirements_builds_tree_when_empty():
    svc = PackTreeService()
    reqs = _reqs("p1",
                 ("A1", "Intro", "KB", "Describe intro."),
                 ("B1.1", "Org \u2014 Organogram", "MANUAL", "Org chart."),
                 ("B1.2", "Org \u2014 Structure", "MANUAL", "Structure."))
    sections = await svc.populate_from_requirements("t", "p1", reqs)
    codes = {s.code: s for s in sections}
    # same grouping as populate_from_extraction: B1.1/B1.2 collapse into one B1 section
    assert set(codes) == {"A1", "B1"}
    b1_qs = await svc.questions.list_for_section("t", codes["B1"].id)
    assert {q.req_id for q in b1_qs} == {"B1.1", "B1.2"}
    assert codes["B1"].name == "Org"  # parent heading before the em-dash
    assert codes["B1"].manual is True and codes["A1"].manual is False


async def test_backfill_from_requirements_is_idempotent():
    svc = PackTreeService()
    reqs = _reqs("p1", ("A1", "Intro", "KB", "Describe intro."))
    first = await svc.populate_from_requirements("t", "p1", reqs)
    assert len(first) == 1
    # a second call must not rebuild or duplicate an already-populated tree
    assert await svc.populate_from_requirements("t", "p1", reqs) == []
    assert len(await svc.sections.list("t", "p1")) == 1
    assert len(await svc.questions.list("t", "p1")) == 1


async def test_backfill_from_requirements_is_tenant_scoped():
    svc = PackTreeService()
    reqs = _reqs("p1", ("A1", "Intro", "KB", "Describe intro."))
    await svc.populate_from_requirements("t", "p1", reqs)
    # another tenant sharing the pack id has its own (initially empty) tree and builds independently
    assert await svc.sections.list("other", "p1") == []
    await svc.populate_from_requirements("other", "p1", reqs)
    assert len(await svc.sections.list("other", "p1")) == 1
    assert len(await svc.sections.list("t", "p1")) == 1  # unaffected


async def test_overview_metrics():
    svc = PackTreeService()
    s = await svc.add_section("t", "p1", code="A1", name="Intro")
    q1 = await svc.add_question("t", s.id, text="Q1")
    await svc.add_question("t", s.id, text="Q2")
    await svc.apply_generation("t", q1.id, ai_answer="draft", ai_sources=["doc:iso"],
                               confidence=0.4, decision="human_review", kb_gap=False)
    ov = await svc.overview("t", "p1")
    assert ov["sections"] == 1 and ov["questions"] == 2
    assert ov["ai_drafted"] == 1 and ov["ai_drafted_total"] == 2
    assert ov["for_human_review"] == 1 and ov["kb_sources"] == 1
    assert ov["can_finalize"] is False


# --- API-level ---
def _pack(client, tenant):
    c = auth_cookies(tenant, "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    return c, pack["id"]


def test_section_question_crud_api(client):
    c, pid = _pack(client, "treeco1")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"code": "A1", "name": "Intro"}, cookies=c).json()
    assert s["status"] == "not_generated"

    q = client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions",
                    json={"text": "Describe X", "word_limit": 100}, cookies=c).json()
    assert q["word_limit"] == 100

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    assert len(tree) == 1 and len(tree[0]["questions"]) == 1

    edited = client.patch(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}",
                          json={"weighting": "20%"}, cookies=c).json()
    assert edited["weighting"] == "20%"

    assert client.delete(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}", cookies=c).json()["deleted"] == q["id"]
    assert client.delete(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}", cookies=c).json()["deleted"] == s["id"]
    assert client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json() == []


def test_mutations_require_editor_role(client):
    owner = auth_cookies("treeco2", "owner")
    pid = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=owner).json()["id"]
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=owner).json()
    viewer = auth_cookies("treeco2", "viewer")
    assert client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "X"}, cookies=viewer).status_code == 403
    assert client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions",
                       json={"text": "Q"}, cookies=viewer).status_code == 403
    # reads stay open to a viewer
    assert client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=viewer).status_code == 200


def test_tree_is_tenant_scoped(client):
    c1, pid = _pack(client, "treet1")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c1).json()
    c2 = auth_cookies("treet2", "owner")
    # cross-tenant cannot see the pack's sections, nor mutate its section
    assert client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c2).status_code == 404
    assert client.patch(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}",
                        json={"name": "hacked"}, cookies=c2).status_code == 404


def _fake_worker_factory(answer="AI draft", grounding=0.9, citations=("doc:iso",),
                         decision=Decision.auto_accept, stub=False):
    class _FakeWorker:
        async def answer(self, rid, text, **_kw):
            return AgentResult(requirement_id=rid, answer=answer,
                               critique=Critique(grounding=grounding), decision=decision,
                               citations=list(citations), stub=stub)

    async def _build(*_a, **_kw):
        return _FakeWorker()
    return _build


def test_generate_question_reuses_agentcore(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.build_tenant_worker", _fake_worker_factory())
    c, pid = _pack(client, "genco1")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    q = client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions",
                    json={"text": "Describe ISO"}, cookies=c).json()

    gen = client.post(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}/generate", cookies=c).json()
    assert gen["ai_answer"] == "AI draft"
    assert gen["confidence"] == 0.9 and gen["decision"] == "auto_accept"
    assert gen["ai_sources"] == ["doc:iso"] and gen["kb_gap"] is False


def test_generate_question_rejects_stub_fallback_and_does_not_persist(client, monkeypatch):
    """When the answer came from the StubProvider fallback (e.g. Bedrock outage), it echoes
    context rather than drafting a real grounded answer. /generate must surface a 503 and must NOT
    persist it onto the question -- otherwise a reviewer could lock and submit a fabricated-looking
    draft. The "real provider persists normally" case is test_generate_question_reuses_agentcore."""
    monkeypatch.setattr("app.modules.rfp.router.build_tenant_worker",
                        _fake_worker_factory(answer="echoed context", stub=True))
    c, pid = _pack(client, "stubgen1")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    q = client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions",
                    json={"text": "Describe ISO"}, cookies=c).json()

    r = client.post(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}/generate", cookies=c)
    assert r.status_code == 503
    # nothing was written onto the question tree
    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    qrow = tree[0]["questions"][0]
    assert qrow["ai_answer"] == "" and qrow["decision"] == ""


def test_generate_flags_kb_gap_when_ungrounded(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.build_tenant_worker",
                        _fake_worker_factory(answer="", grounding=0.0, citations=(),
                                             decision=Decision.human_review))
    c, pid = _pack(client, "genco2")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    q = client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions",
                    json={"text": "Unknown"}, cookies=c).json()
    gen = client.post(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}/generate", cookies=c).json()
    assert gen["kb_gap"] is True and gen["decision"] == "human_review"


def test_generate_section_and_pack(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.build_tenant_worker", _fake_worker_factory())
    c, pid = _pack(client, "genco3")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions", json={"text": "Q1"}, cookies=c)
    client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions", json={"text": "Q2"}, cookies=c)

    sec_gen = client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/generate", cookies=c).json()
    assert len(sec_gen) == 2 and all(g["ai_answer"] == "AI draft" for g in sec_gen)

    pack_gen = client.post(f"/api/v1/rfp/packs/{pid}/generate", cookies=c).json()
    assert len(pack_gen) == 2


def test_save_draft_lock_unlock_and_stage_guard(client):
    c, pid = _pack(client, "lockco1")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    q = client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions",
                    json={"text": "Q1"}, cookies=c).json()

    drafted = client.put(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}/draft",
                         json={"user_draft": "my answer"}, cookies=c).json()
    assert drafted["user_draft"] == "my answer"

    # cannot finalise before all sections are locked
    assert client.put(f"/api/v1/rfp/packs/{pid}/stage", json={"stage": "final"}, cookies=c).status_code == 409

    locked = client.post(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}/lock", cookies=c).json()
    assert locked["locked"] is True
    ov = client.get(f"/api/v1/rfp/packs/{pid}/overview", cookies=c).json()
    assert ov["sections_locked"] == 1 and ov["can_finalize"] is True

    # now the pack can advance to final
    assert client.put(f"/api/v1/rfp/packs/{pid}/stage", json={"stage": "final"}, cookies=c).json()["stage"] == "final"

    client.post(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}/unlock", cookies=c)
    assert client.get(f"/api/v1/rfp/packs/{pid}/overview", cookies=c).json()["can_finalize"] is False


def test_extract_populates_tree_and_lock_all(client, monkeypatch):
    import json as _json
    payload = _json.dumps([
        {"id": "A1", "title": "ISO", "classification": "KB", "requirement": "Describe ISO."},
        {"id": "A2", "title": "Pricing", "classification": "MANUAL", "requirement": "Complete pricing."},
    ])

    def fake_get_provider(**_kw):
        class P:
            def generate(self, prompt, *, system=None, temperature=0.2):
                from app.modules.ai.gateway import LLMResponse
                return LLMResponse(text=payload)
        return P()

    monkeypatch.setattr("app.modules.rfp.generation.get_provider", fake_get_provider)
    monkeypatch.setattr("app.modules.rfp.generation.assemble_worker", _fake_worker_factory(stub=True))
    c, pid = _pack(client, "extrco1")
    client.post(f"/api/v1/rfp/packs/{pid}/extract", cookies=c,
                files={"file": ("t.txt", io.BytesIO(b"tender"), "text/plain")})

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    codes = {s["code"]: s for s in tree}
    assert set(codes) == {"A1", "A2"}
    assert codes["A2"]["manual"] is True
    assert len(codes["A1"]["questions"]) == 1


def test_sections_backfill_lazily_for_old_pack(client, monkeypatch):
    """A pack that pre-dates the tree feature has flat requirements but an empty tree; GET /sections
    backfills it lazily from those requirements (no LLM), and repeat views stay idempotent."""
    import json as _json
    payload = _json.dumps([
        {"id": "A1", "title": "ISO", "classification": "KB", "requirement": "Describe ISO."},
        {"id": "B1.1", "title": "Org \u2014 Organogram", "classification": "MANUAL", "requirement": "Chart."},
        {"id": "B1.2", "title": "Org \u2014 Structure", "classification": "MANUAL", "requirement": "Structure."},
    ])

    def fake_get_provider(**_kw):
        class P:
            def generate(self, prompt, *, system=None, temperature=0.2):
                from app.modules.ai.gateway import LLMResponse
                return LLMResponse(text=payload)
        return P()

    monkeypatch.setattr("app.modules.rfp.generation.get_provider", fake_get_provider)
    monkeypatch.setattr("app.modules.rfp.generation.assemble_worker", _fake_worker_factory(stub=True))
    c, pid = _pack(client, "backfillco1")
    client.post(f"/api/v1/rfp/packs/{pid}/extract", cookies=c,
                files={"file": ("t.txt", io.BytesIO(b"tender"), "text/plain")})

    # simulate an old pack: keep the extracted requirements but wipe the tree the new /extract built
    for s in client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json():
        client.delete(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}", cookies=c)

    # first view backfills the tree from the stored requirements
    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    codes = {s["code"]: s for s in tree}
    assert set(codes) == {"A1", "B1"}
    assert len(codes["B1"]["questions"]) == 2 and codes["B1"]["manual"] is True

    # idempotent: a second view neither rebuilds nor duplicates
    again = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    assert {s["id"] for s in again} == {s["id"] for s in tree}


def test_export_overlay_locked_user_draft_overrides_ai(client, monkeypatch):
    import json as _json
    payload = _json.dumps([
        {"id": "A1", "title": "ISO", "classification": "KB", "requirement": "Describe ISO."},
    ])

    def fake_get_provider(**_kw):
        class P:
            def generate(self, prompt, *, system=None, temperature=0.2):
                from app.modules.ai.gateway import LLMResponse
                return LLMResponse(text=payload)
        return P()

    monkeypatch.setattr("app.modules.rfp.generation.get_provider", fake_get_provider)
    monkeypatch.setattr("app.modules.rfp.generation.assemble_worker", _fake_worker_factory(stub=True))
    monkeypatch.setattr("app.modules.rfp.router.build_tenant_worker",
                        _fake_worker_factory(answer="AI generated answer"))
    c, pid = _pack(client, "ovlyco1")
    client.post(f"/api/v1/rfp/packs/{pid}/extract", cookies=c,
                files={"file": ("t.txt", io.BytesIO(b"tender"), "text/plain")})

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    qid = tree[0]["questions"][0]["id"]
    client.put(f"/api/v1/rfp/packs/{pid}/questions/{qid}/draft",
               json={"user_draft": "HUMAN APPROVED TEXT"}, cookies=c)
    client.post(f"/api/v1/rfp/packs/{pid}/questions/{qid}/lock", cookies=c)

    answers = client.get(f"/api/v1/rfp/packs/{pid}/answers", cookies=c).json()
    a1 = next(a for a in answers if a["req_id"] == "A1")
    assert a1["answer"] == "HUMAN APPROVED TEXT"  # locked draft overrides the AI answer
    assert "human-approved" in a1["note"].lower()
