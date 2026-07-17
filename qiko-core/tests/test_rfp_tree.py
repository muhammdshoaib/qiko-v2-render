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


async def test_extraction_wiring_builds_two_level_tree():
    svc = PackTreeService()
    extracted = [
        {"id": "A1", "title": "Intro", "classification": "KB", "requirement": "Describe intro."},
        {"id": "B1.1", "title": "Org \u2014 Organogram", "classification": "KB", "requirement": "Org chart."},
        {"id": "B1.2", "title": "Org \u2014 Structure", "classification": "KB", "requirement": "Structure."},
        {"id": "C1", "title": "Pricing", "classification": "MANUAL", "requirement": "Complete pricing."},
    ]
    await svc.populate_from_extraction("t", "p1", extracted)
    sections = await svc.sections.list("t", "p1")
    codes = {s.code: s for s in sections}
    # top-level sections A1/B1/C1 plus B1's two child sub-sections
    top = {s.code for s in sections if s.parent_id is None}
    assert top == {"A1", "B1", "C1"}
    b1 = codes["B1"]
    # B1 is a PARENT: no direct questions, two child sub-sections (B1.1, B1.2), each one question
    assert await svc.questions.list_for_section("t", b1.id) == []
    kids = [s for s in sections if s.parent_id == b1.id]
    assert {k.code for k in kids} == {"B1.1", "B1.2"}
    assert codes["B1"].name == "Org"  # parent heading before the em-dash
    assert codes["B1.1"].name == "Organogram" and codes["B1.2"].name == "Structure"
    for k in kids:
        kq = await svc.questions.list_for_section("t", k.id)
        assert len(kq) == 1 and kq[0].req_id == k.code
    # A1 (no dotted children) keeps a single question directly on the section
    a1_qs = await svc.questions.list_for_section("t", codes["A1"].id)
    assert len(a1_qs) == 1 and a1_qs[0].req_id == "A1"
    # a section whose items are all MANUAL/COMPLIANCE is flagged manual
    assert codes["C1"].manual is True and codes["A1"].manual is False


async def test_build_tree_yields_few_top_level_sections_from_many_items():
    """BOC-style input: many fine-grained sub-parts collapse under a handful of top-level
    sections (~idg's ~15), not one top-level section per item."""
    svc = PackTreeService()
    extracted = [{"id": "A1", "title": "Commercial", "classification": "MANUAL", "requirement": "Forms."}]
    for sec in range(1, 6):  # B1..B5, each with 6 dotted sub-parts -> 30 sub-parts
        for sub in range(1, 7):
            extracted.append({"id": f"B{sec}.{sub}", "title": f"Section {sec} \u2014 Part {sub}",
                              "classification": "KB", "requirement": f"Describe B{sec}.{sub}."})
    await svc.populate_from_extraction("t", "pboc", extracted)
    sections = await svc.sections.list("t", "pboc")
    top = [s for s in sections if s.parent_id is None]
    assert len(top) == 6  # A1 + B1..B5, far fewer than the 31 extracted items
    assert len(top) < len(extracted)
    # every top-level B section carries 6 sub-sections; the sub-sections hold the questions
    assert all(len([s for s in sections if s.parent_id == p.id]) == 6
               for p in top if p.code.startswith("B"))
    assert len(await svc.questions.list("t", "pboc")) == 31  # one leaf question per item


async def test_build_tree_derives_subsections_from_requirement_text():
    """Coarse+split model (idg quality): a SINGLE coarse extracted section whose requirement text
    embeds dotted "B1.1/B1.2" sub-parts expands into two child sub-sections derived from the text
    -- the extractor did NOT emit them as separate items."""
    svc = PackTreeService()
    extracted = [{
        "id": "B1", "title": "Organisational Structure & Manpower", "classification": "KB",
        "requirement": ("B1.1 Contractor's Organogram: provide an organisation chart.\n"
                        "B1.2 Contractor's Organisation: describe the management structure."),
    }]
    await svc.populate_from_extraction("t", "psplit", extracted)
    sections = await svc.sections.list("t", "psplit")
    top = [s for s in sections if s.parent_id is None]
    assert len(top) == 1 and top[0].code == "B1"  # ONE top-level coarse section
    # its two sub-sections were derived from the requirement text
    kids = [s for s in sections if s.parent_id == top[0].id]
    assert {k.code for k in kids} == {"B1.1", "B1.2"}
    # the parent holds no direct question; each child holds its own single question
    assert await svc.questions.list_for_section("t", top[0].id) == []
    for k in kids:
        assert len(await svc.questions.list_for_section("t", k.id)) == 1


async def test_build_tree_coarse_items_yield_at_most_that_many_top_level_sections():
    """20 coarse extracted items (each a whole top-level section, single-sentence requirement)
    yield 20 top-level sections -- no over-granular explosion, matching idg's ~10-20 catalogue."""
    svc = PackTreeService()
    extracted = [{"id": f"S{i}", "title": f"Section {i}", "classification": "KB",
                  "requirement": f"Describe section {i}."} for i in range(1, 21)]
    await svc.populate_from_extraction("t", "pcoarse", extracted)
    sections = await svc.sections.list("t", "pcoarse")
    top = [s for s in sections if s.parent_id is None]
    assert len(top) == 20  # one coarse top-level section per item, none split
    assert not [s for s in sections if s.parent_id is not None]  # no sub-sections
    assert len(await svc.questions.list("t", "pcoarse")) == 20  # one question per section


async def test_build_tree_coalesces_flat_legacy_ids():
    """An old flat backfill emits non-dotted ids like 'A1_unpriced'/'A1_priced'; they must group
    by leading section token, not each become a top-level section."""
    svc = PackTreeService()
    extracted = [
        {"id": "A1_unpriced", "title": "Pricing", "classification": "MANUAL", "requirement": "Unpriced BOQ."},
        {"id": "A1_priced", "title": "Pricing", "classification": "MANUAL", "requirement": "Priced BOQ."},
        {"id": "2", "title": "Declaration", "classification": "COMPLIANCE", "requirement": "Sign."},
    ]
    await svc.populate_from_extraction("t", "pflat", extracted)
    sections = await svc.sections.list("t", "pflat")
    top = {s.code for s in sections if s.parent_id is None}
    assert top == {"A1", "2"}  # the two A1_* ids coalesce under one top-level "A1"
    a1 = next(s for s in sections if s.code == "A1")
    a1_qs = await svc.questions.list_for_section("t", a1.id)
    assert {q.req_id for q in a1_qs} == {"A1_unpriced", "A1_priced"}


async def test_parent_section_rolls_up_kb_gap_confidence_grounding_from_children():
    svc = PackTreeService()
    extracted = [
        {"id": "B1.1", "title": "Org \u2014 Organogram", "classification": "KB", "requirement": "Chart."},
        {"id": "B1.2", "title": "Org \u2014 Structure", "classification": "KB", "requirement": "Structure."},
    ]
    await svc.populate_from_extraction("t", "proll", extracted)
    sections = {s.code: s for s in await svc.sections.list("t", "proll")}
    b1_1_q = (await svc.questions.list_for_section("t", sections["B1.1"].id))[0]
    b1_2_q = (await svc.questions.list_for_section("t", sections["B1.2"].id))[0]
    # one child grounded, the other a KB gap
    await svc.apply_generation("t", b1_1_q.id, ai_answer="draft", ai_sources=["doc:iso"],
                               confidence=0.8, decision="auto_accept", kb_gap=False)
    await svc.apply_generation("t", b1_2_q.id, ai_answer="draft", ai_sources=[],
                               confidence=0.4, decision="human_review", kb_gap=True)
    # the stored parent section now reflects the child KB gap (drives the FE Gaps column)
    assert (await svc.get_section("t", sections["B1"].id)).kb_gap is True

    tree = await svc.list_tree("t", "proll")
    node = {n["code"]: n for n in tree}
    b1 = node["B1"]
    assert b1["kb_gap"] is True                    # any child is a KB gap
    assert b1["confidence"] == 0.6                 # avg of drafted children (0.8, 0.4)
    assert b1["grounding"] == 0.6
    assert b1["subsection_count"] == 2
    assert b1["questions"] == []                   # parent has no direct questions
    # per-sub-section rollup stays scoped to that sub-section
    assert node["B1.1"]["confidence"] == 0.8 and node["B1.1"]["kb_gap"] is False
    assert node["B1.2"]["confidence"] == 0.4 and node["B1.2"]["kb_gap"] is True


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
    await svc.populate_from_requirements("t", "p1", reqs)
    sections = await svc.sections.list("t", "p1")
    codes = {s.code: s for s in sections}
    # same two-level grouping as populate_from_extraction: B1.1/B1.2 become sub-sections under B1
    top = {s.code for s in sections if s.parent_id is None}
    assert top == {"A1", "B1"}
    assert await svc.questions.list_for_section("t", codes["B1"].id) == []
    kids = {s.code for s in sections if s.parent_id == codes["B1"].id}
    assert kids == {"B1.1", "B1.2"}
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
    # ai_drafted is counted per top-level SECTION (like idg's 8/15), not per question: the one
    # section has a draft, so 1/1 (not 1/2).
    assert ov["ai_drafted"] == 1 and ov["ai_drafted_total"] == 1
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
    # A1 (plain) is a top-level section; B1 is a parent with two child sub-sections (B1.1, B1.2)
    assert {s["code"] for s in tree if s["parent_id"] is None} == {"A1", "B1"}
    assert codes["B1"]["questions"] == [] and codes["B1"]["manual"] is True
    assert codes["B1"]["subsection_count"] == 2
    assert {s["code"] for s in tree if s["parent_id"] == codes["B1"]["id"]} == {"B1.1", "B1.2"}

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


# --- stepper: per-section reviewer assignment, assignees list, confirm-assignments flag ---
def test_set_and_clear_section_reviewer_persists(client):
    c, pid = _pack(client, "revco1")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    assert s["reviewer"] is None and s["reviewer_name"] == ""

    # assign a reviewer (id + denormalised display name)
    assigned = client.put(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/reviewer",
                          json={"reviewer": "u-alice", "reviewer_name": "Alice"}, cookies=c).json()
    assert assigned["reviewer"] == "u-alice" and assigned["reviewer_name"] == "Alice"

    # it persists onto the section and shows in the sections GET (Reviewer column source)
    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    assert tree[0]["reviewer"] == "u-alice" and tree[0]["reviewer_name"] == "Alice"

    # null clears it
    cleared = client.put(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/reviewer",
                        json={"reviewer": None}, cookies=c).json()
    assert cleared["reviewer"] is None and cleared["reviewer_name"] == ""
    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    assert tree[0]["reviewer"] is None


def test_set_reviewer_requires_editor_and_is_tenant_scoped(client):
    c, pid = _pack(client, "revco2")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    viewer = auth_cookies("revco2", "viewer")
    assert client.put(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/reviewer",
                      json={"reviewer": "u-alice"}, cookies=viewer).status_code == 403
    # another tenant cannot assign a reviewer on this pack's section
    other = auth_cookies("revco2-other", "owner")
    assert client.put(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/reviewer",
                      json={"reviewer": "u-mallory"}, cookies=other).status_code == 404


def test_assignees_lists_tenant_users(client):
    from app.modules.identity.router import get_store
    from app.modules.identity.rbac import Role
    from app.modules.identity.store import User

    store = get_store()
    store.seed(User(id="u-a", email="alice@assignco.com", password_hash="x",
                    tenant="assignco", role=Role.editor))
    store.seed(User(id="u-b", email="bob@assignco.com", password_hash="x",
                    tenant="assignco", role=Role.viewer))
    # a different tenant's user must not leak into assignco's dropdown
    store.seed(User(id="u-x", email="x@other.com", password_hash="x", tenant="otherco", role=Role.owner))

    c = auth_cookies("assignco", "owner")
    pid = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()["id"]
    people = client.get(f"/api/v1/rfp/packs/{pid}/assignees", cookies=c).json()
    ids = {p["id"] for p in people}
    assert ids == {"u-a", "u-b"}
    alice = next(p for p in people if p["id"] == "u-a")
    assert alice["email"] == "alice@assignco.com" and alice["name"] == "alice"


def test_confirm_assignments_sets_flag_in_gen_status(client):
    c, pid = _pack(client, "confirmco1")
    # before confirming, the flag is absent from gen_status
    assert "assignments_confirmed" not in client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()

    out = client.post(f"/api/v1/rfp/packs/{pid}/confirm-assignments", cookies=c).json()
    assert out["assignments_confirmed"] is True

    # GET /status now reflects the stepper-progression marker for the FE
    status = client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json()
    assert status["assignments_confirmed"] is True

    # editor-gated
    viewer = auth_cookies("confirmco1", "viewer")
    assert client.post(f"/api/v1/rfp/packs/{pid}/confirm-assignments", cookies=viewer).status_code == 403


async def test_set_reviewer_service_clears_with_none():
    svc = PackTreeService()
    s = await svc.add_section("t", "p1", code="A1", name="Intro")
    assigned = await svc.set_reviewer("t", s.id, reviewer="u-alice", reviewer_name="Alice")
    assert assigned.reviewer == "u-alice" and assigned.reviewer_name == "Alice"
    cleared = await svc.set_reviewer("t", s.id, reviewer=None)
    assert cleared.reviewer is None and cleared.reviewer_name == ""
