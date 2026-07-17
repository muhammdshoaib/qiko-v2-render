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
        {"id": "A1", "title": "Intro", "classification": "KB", "requirement": "Describe intro.",
         "subsections": []},
        {"id": "B1", "title": "Org", "classification": "KB", "requirement": "Describe org.",
         "subsections": [
             {"id": "B1.1", "title": "Organogram", "classification": "KB", "requirement": "Org chart."},
             {"id": "B1.2", "title": "Structure", "classification": "KB", "requirement": "Structure."},
         ]},
        {"id": "C1", "title": "Pricing", "classification": "MANUAL", "requirement": "Complete pricing.",
         "subsections": []},
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
    assert codes["B1"].name == "Org"  # the section's own explicit title
    assert codes["B1.1"].name == "Organogram" and codes["B1.2"].name == "Structure"
    for k in kids:
        kq = await svc.questions.list_for_section("t", k.id)
        assert len(kq) == 1 and kq[0].req_id == k.code
    # A1 (no sub-sections) keeps a single question directly on the section
    a1_qs = await svc.questions.list_for_section("t", codes["A1"].id)
    assert len(a1_qs) == 1 and a1_qs[0].req_id == "A1"
    # a section whose items are all MANUAL/COMPLIANCE is flagged manual
    assert codes["C1"].manual is True and codes["A1"].manual is False


async def test_build_tree_yields_few_top_level_sections_from_explicit_subsections():
    """BOC-style input: many fine-grained sub-parts are nested as EXPLICIT sub-sections under a
    handful of top-level sections (~idg's ~15), not one top-level section per sub-part."""
    svc = PackTreeService()
    extracted = [{"id": "A1", "title": "Commercial", "classification": "MANUAL", "requirement": "Forms.",
                  "subsections": []}]
    for sec in range(1, 6):  # B1..B5, each with 6 explicit sub-parts -> 30 sub-parts
        extracted.append({
            "id": f"B{sec}", "title": f"Section {sec}", "classification": "KB",
            "requirement": f"Describe B{sec}.",
            "subsections": [{"id": f"B{sec}.{sub}", "title": f"Part {sub}", "classification": "KB",
                             "requirement": f"Describe B{sec}.{sub}."} for sub in range(1, 7)],
        })
    await svc.populate_from_extraction("t", "pboc", extracted)
    sections = await svc.sections.list("t", "pboc")
    top = [s for s in sections if s.parent_id is None]
    assert len(top) == 6  # A1 + B1..B5, far fewer than the 31 leaf answers
    # every top-level B section carries 6 sub-sections; the sub-sections hold the questions
    assert all(len([s for s in sections if s.parent_id == p.id]) == 6
               for p in top if p.code.startswith("B"))
    # 30 sub-section leaf questions + 1 on childless A1
    assert len(await svc.questions.list("t", "pboc")) == 31


async def test_build_tree_section_with_explicit_subsections_builds_parent_and_children():
    """A single section with an EXPLICIT `subsections` array deterministically builds one parent
    plus one child sub-section per entry -- no dependence on markers in the requirement prose."""
    svc = PackTreeService()
    extracted = [{
        "id": "B1", "title": "Organisational Structure & Manpower", "classification": "KB",
        "requirement": "Describe your organisational structure.",
        "subsections": [
            {"id": "B1.1", "title": "Organogram", "classification": "KB",
             "requirement": "Provide an organisation chart."},
            {"id": "B1.2", "title": "Management", "classification": "KB",
             "requirement": "Describe the management structure."},
        ],
    }]
    await svc.populate_from_extraction("t", "psplit", extracted)
    sections = await svc.sections.list("t", "psplit")
    top = [s for s in sections if s.parent_id is None]
    assert len(top) == 1 and top[0].code == "B1"  # ONE top-level section
    kids = [s for s in sections if s.parent_id == top[0].id]
    assert {k.code for k in kids} == {"B1.1", "B1.2"}
    # the parent holds no direct question; each child holds its own single question
    assert await svc.questions.list_for_section("t", top[0].id) == []
    for k in kids:
        assert len(await svc.questions.list_for_section("t", k.id)) == 1


async def test_build_tree_section_with_empty_subsections_builds_single_leaf():
    """A section with an empty `subsections` array is a single leaf: one top-level section with one
    question (its own requirement) and no children."""
    svc = PackTreeService()
    extracted = [{"id": "A1", "title": "Company Profile", "classification": "KB",
                  "requirement": "Describe your company.", "subsections": []}]
    await svc.populate_from_extraction("t", "pleaf", extracted)
    sections = await svc.sections.list("t", "pleaf")
    assert len(sections) == 1 and sections[0].parent_id is None
    qs = await svc.questions.list_for_section("t", sections[0].id)
    assert len(qs) == 1 and qs[0].req_id == "A1"
    assert qs[0].text == "Describe your company."


async def test_build_tree_coarse_items_yield_at_most_that_many_top_level_sections():
    """20 coarse extracted sections (each a whole top-level section, no sub-sections) yield 20
    top-level sections -- no over-granular explosion, matching idg's ~10-20 catalogue."""
    svc = PackTreeService()
    extracted = [{"id": f"S{i}", "title": f"Section {i}", "classification": "KB",
                  "requirement": f"Describe section {i}.", "subsections": []} for i in range(1, 21)]
    await svc.populate_from_extraction("t", "pcoarse", extracted)
    sections = await svc.sections.list("t", "pcoarse")
    top = [s for s in sections if s.parent_id is None]
    assert len(top) == 20  # one coarse top-level section per item, none split
    assert not [s for s in sections if s.parent_id is not None]  # no sub-sections
    assert len(await svc.questions.list("t", "pcoarse")) == 20  # one question per section


async def test_build_tree_coalesces_flat_legacy_ids():
    """An old flat backfill (populate_from_requirements) emits non-dotted ids like
    'A1_unpriced'/'A1_priced'; the LEGACY coalescing path groups them by leading section token,
    not each becoming a top-level section."""
    svc = PackTreeService()
    reqs = _reqs("pflat",
                 ("A1_unpriced", "Pricing", "MANUAL", "Unpriced BOQ."),
                 ("A1_priced", "Pricing", "MANUAL", "Priced BOQ."),
                 ("2", "Declaration", "COMPLIANCE", "Sign."))
    await svc.populate_from_requirements("t", "pflat", reqs)
    sections = await svc.sections.list("t", "pflat")
    top = {s.code for s in sections if s.parent_id is None}
    assert top == {"A1", "2"}  # the two A1_* ids coalesce under one top-level "A1"
    a1 = next(s for s in sections if s.code == "A1")
    a1_qs = await svc.questions.list_for_section("t", a1.id)
    assert {q.req_id for q in a1_qs} == {"A1_unpriced", "A1_priced"}


async def test_parent_section_rolls_up_kb_gap_confidence_grounding_from_children():
    svc = PackTreeService()
    extracted = [{
        "id": "B1", "title": "Org", "classification": "KB", "requirement": "Describe org.",
        "subsections": [
            {"id": "B1.1", "title": "Organogram", "classification": "KB", "requirement": "Chart."},
            {"id": "B1.2", "title": "Structure", "classification": "KB", "requirement": "Structure."},
        ],
    }]
    await svc.populate_from_extraction("t", "proll", extracted)
    sections = {s.code: s for s in await svc.sections.list("t", "proll")}
    b1_1_q = (await svc.questions.list_for_section("t", sections["B1.1"].id))[0]
    b1_2_q = (await svc.questions.list_for_section("t", sections["B1.2"].id))[0]
    # one child grounded, the other a KB gap. confidence (writer self-report) and grounding
    # (independent critic) are DISTINCT numbers per child, so the parent averages them separately.
    await svc.apply_generation("t", b1_1_q.id, ai_answer="draft", ai_sources=["doc:iso"],
                               confidence=0.8, grounding=0.9, gaps="", decision="auto_accept",
                               kb_gap=False)
    await svc.apply_generation("t", b1_2_q.id, ai_answer="draft", ai_sources=[],
                               confidence=0.4, grounding=0.3, gaps="no pricing evidence",
                               decision="human_review", kb_gap=True)
    # the stored parent section now reflects the child KB gap (drives the FE Gaps column)
    assert (await svc.get_section("t", sections["B1"].id)).kb_gap is True

    tree = await svc.list_tree("t", "proll")
    node = {n["code"]: n for n in tree}
    b1 = node["B1"]
    assert b1["kb_gap"] is True                    # any child is a KB gap
    assert b1["confidence"] == 0.6                 # avg confidence of drafted children (0.8, 0.4)
    assert b1["grounding"] == 0.6                  # avg grounding of drafted children (0.9, 0.3)
    assert b1["subsection_count"] == 2
    assert b1["questions"] == []                   # parent has no direct questions
    # per-sub-section rollup stays scoped to that sub-section, with distinct confidence/grounding
    assert node["B1.1"]["confidence"] == 0.8 and node["B1.1"]["grounding"] == 0.9
    assert node["B1.1"]["kb_gap"] is False
    assert node["B1.2"]["confidence"] == 0.4 and node["B1.2"]["grounding"] == 0.3
    assert node["B1.2"]["kb_gap"] is True


async def test_section_kb_gap_pill_lights_up_for_gaps_text_without_kb_gap_flag():
    """The listing KB-gap pill (section.kb_gap, rolled up in list_tree) must be consistent with the
    detail "Gaps for human input" box: a question with a non-empty gaps note but kb_gap=False still
    "has a gap", so its section must show the pill."""
    svc = PackTreeService()
    extracted = [{
        "id": "A6", "title": "BOC A6", "classification": "KB", "requirement": "Answer A6.",
        "subsections": [
            {"id": "A6.1", "title": "Part one", "classification": "KB", "requirement": "One."},
        ],
    }]
    await svc.populate_from_extraction("t", "pgap", extracted)
    sections = {s.code: s for s in await svc.sections.list("t", "pgap")}
    a6_1_q = (await svc.questions.list_for_section("t", sections["A6.1"].id))[0]
    # grounded above threshold (kb_gap=False) but the writer flagged missing evidence in gaps text
    await svc.apply_generation("t", a6_1_q.id, ai_answer="draft", ai_sources=["doc:iso"],
                               confidence=0.9, grounding=0.9, gaps="missing recent case study",
                               decision="auto_accept", kb_gap=False)
    # stored rollup + serialized nodes both raise the pill off the gaps text alone
    assert (await svc.get_section("t", sections["A6"].id)).kb_gap is True
    node = {n["code"]: n for n in await svc.list_tree("t", "pgap")}
    assert node["A6"]["kb_gap"] is True    # parent rolls up the child's gaps text
    assert node["A6.1"]["kb_gap"] is True  # the leaf itself has a gap despite kb_gap=False


async def test_section_kb_gap_pill_off_when_no_gap_flag_and_no_gaps_text():
    """The inverse: a fully-grounded answer with no gaps text and kb_gap=False shows no pill."""
    svc = PackTreeService()
    extracted = [{
        "id": "A7", "title": "BOC A7", "classification": "KB", "requirement": "Answer A7.",
        "subsections": [
            {"id": "A7.1", "title": "Part one", "classification": "KB", "requirement": "One."},
        ],
    }]
    await svc.populate_from_extraction("t", "pnogap", extracted)
    sections = {s.code: s for s in await svc.sections.list("t", "pnogap")}
    a7_1_q = (await svc.questions.list_for_section("t", sections["A7.1"].id))[0]
    await svc.apply_generation("t", a7_1_q.id, ai_answer="draft", ai_sources=["doc:iso"],
                               confidence=0.9, grounding=0.9, gaps="   ",
                               decision="auto_accept", kb_gap=False)
    assert (await svc.get_section("t", sections["A7"].id)).kb_gap is False
    node = {n["code"]: n for n in await svc.list_tree("t", "pnogap")}
    assert node["A7"]["kb_gap"] is False
    assert node["A7.1"]["kb_gap"] is False


async def test_manual_section_satisfies_finalize_gate():
    """H1: a MANUAL (human-owned) section is never AI-lockable, so it must COUNT as satisfying the
    finalize gate -- otherwise any pack with a manual/compliance section could never finalize."""
    svc = PackTreeService()
    m = await svc.add_section("t", "p1", code="A1", name="Pricing", manual=True)
    assert (await svc.get_section("t", m.id)).status == "manual"
    # a lone manual section already satisfies the gate
    assert await svc.all_sections_locked("t", "p1")

    # add a normal (AI) section: finalize is now blocked until its question is locked
    n = await svc.add_section("t", "p1", code="B1", name="Method")
    q = await svc.add_question("t", n.id, text="Describe your method")
    assert not await svc.all_sections_locked("t", "p1")
    await svc.lock_question("t", q.id)
    assert await svc.all_sections_locked("t", "p1")


async def test_manual_parent_and_mixed_parent_finalize_correctly():
    """H1: a fully-manual parent (manual children) stays "manual" and satisfies the gate, and a
    MIXED parent (a manual child + an AI child) reaches "locked" once its AI child is locked."""
    svc = PackTreeService()
    extracted = [
        {"id": "A1", "title": "Commercial", "classification": "KB", "requirement": "Section.",
         "subsections": [
             {"id": "A1.1", "title": "Forms", "classification": "MANUAL", "requirement": "Fill forms."},
             {"id": "A1.2", "title": "Method", "classification": "KB", "requirement": "Describe method."},
         ]},
        {"id": "B1", "title": "Pricing", "classification": "MANUAL", "requirement": "Pricing.",
         "subsections": [
             {"id": "B1.1", "title": "Priced", "classification": "MANUAL", "requirement": "Priced BOQ."},
             {"id": "B1.2", "title": "Unpriced", "classification": "COMPLIANCE", "requirement": "Unpriced BOQ."},
         ]},
    ]
    await svc.populate_from_extraction("t", "pmix", extracted)
    codes = {s.code: s for s in await svc.sections.list("t", "pmix")}
    # B1 is a fully-manual parent -> "manual" (not spuriously flipped to "locked")
    assert codes["B1"].status == "manual"
    # A1 is a mixed parent -> not manual, still blocking until its AI child (A1.2) is locked
    assert codes["A1"].status != "locked"
    assert not await svc.all_sections_locked("t", "pmix")

    a12_q = (await svc.questions.list_for_section("t", codes["A1.2"].id))[0]
    await svc.lock_question("t", a12_q.id)
    # the manual child A1.1 satisfies the gate, so locking the AI child locks the parent
    assert (await svc.get_section("t", codes["A1"].id)).status == "locked"
    assert await svc.all_sections_locked("t", "pmix")


async def test_overview_counts_parent_with_own_drafted_question():
    """M4: a legacy flat-path parent can carry BOTH its own questions AND child sub-sections. The
    overview must count it as drafted when its OWN question is drafted, not only when a child is."""
    svc = PackTreeService()
    reqs = _reqs("pm4",
                 ("A1", "Intro", "KB", "Describe intro."),        # plain -> a question ON the parent
                 ("A1.1", "Intro \u2014 Detail", "KB", "Detail."))  # dotted -> a child sub-section
    await svc.populate_from_requirements("t", "pm4", reqs)
    parent = next(s for s in await svc.sections.list("t", "pm4") if s.code == "A1")
    own = await svc.questions.list_for_section("t", parent.id)
    assert own and own[0].req_id == "A1"  # the parent owns a direct question

    # draft ONLY the parent's own question, leaving the child sub-section un-drafted
    await svc.apply_generation("t", own[0].id, ai_answer="draft", ai_sources=["doc:iso"],
                               confidence=0.7, decision="auto_accept", kb_gap=False)
    ov = await svc.overview("t", "pm4")
    assert ov["ai_drafted"] == 1 and ov["ai_drafted_total"] == 1


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


def _fake_worker_factory(answer="AI draft", grounding=0.9, confidence=None, gaps="",
                         citations=("doc:iso",), decision=Decision.auto_accept, stub=False):
    # confidence defaults to the grounding value only so callers that don't care keep the old
    # behaviour; tests that assert the two are DISTINCT pass an explicit confidence.
    conf = grounding if confidence is None else confidence

    class _FakeWorker:
        async def answer(self, rid, text, **_kw):
            return AgentResult(requirement_id=rid, answer=answer,
                               critique=Critique(grounding=grounding), decision=decision,
                               citations=list(citations), confidence=conf, gaps=gaps, stub=stub)

    async def _build(*_a, **_kw):
        return _FakeWorker()
    return _build


def test_generate_question_reuses_agentcore(client, monkeypatch):
    # confidence (writer self-report) and grounding (independent critic) are DISTINCT and both
    # persisted, along with the writer's gaps note.
    monkeypatch.setattr("app.modules.rfp.router.build_tenant_worker",
                        _fake_worker_factory(grounding=0.9, confidence=0.7, gaps="no SLA evidence"))
    c, pid = _pack(client, "genco1")
    s = client.post(f"/api/v1/rfp/packs/{pid}/sections", json={"name": "Intro"}, cookies=c).json()
    q = client.post(f"/api/v1/rfp/packs/{pid}/sections/{s['id']}/questions",
                    json={"text": "Describe ISO"}, cookies=c).json()

    gen = client.post(f"/api/v1/rfp/packs/{pid}/questions/{q['id']}/generate", cookies=c).json()
    assert gen["ai_answer"] == "AI draft"
    assert gen["confidence"] == 0.7 and gen["grounding"] == 0.9 and gen["decision"] == "auto_accept"
    assert gen["gaps"] == "no SLA evidence"
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
            def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
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


def test_manual_section_does_not_block_finalize_api(client, monkeypatch):
    """H1 end-to-end: a pack with a MANUAL section (A2) can still finalize once the AI section (A1)
    is locked -- the manual section counts as satisfied instead of blocking forever with a 409."""
    import json as _json
    payload = _json.dumps([
        {"id": "A1", "title": "ISO", "classification": "KB", "requirement": "Describe ISO."},
        {"id": "A2", "title": "Pricing", "classification": "MANUAL", "requirement": "Complete pricing."},
    ])

    def fake_get_provider(**_kw):
        class P:
            def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
                from app.modules.ai.gateway import LLMResponse
                return LLMResponse(text=payload)
        return P()

    monkeypatch.setattr("app.modules.rfp.generation.get_provider", fake_get_provider)
    monkeypatch.setattr("app.modules.rfp.generation.assemble_worker", _fake_worker_factory(stub=True))
    c, pid = _pack(client, "finalmanual1")
    client.post(f"/api/v1/rfp/packs/{pid}/extract", cookies=c,
                files={"file": ("t.txt", io.BytesIO(b"tender"), "text/plain")})

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    codes = {s["code"]: s for s in tree}
    assert codes["A2"]["manual"] is True
    # cannot finalize yet: the AI section A1 is not locked
    assert client.put(f"/api/v1/rfp/packs/{pid}/stage", json={"stage": "final"}, cookies=c).status_code == 409

    a1_q = codes["A1"]["questions"][0]["id"]
    client.post(f"/api/v1/rfp/packs/{pid}/questions/{a1_q}/lock", cookies=c)
    ov = client.get(f"/api/v1/rfp/packs/{pid}/overview", cookies=c).json()
    assert ov["can_finalize"] is True  # A1 locked + A2 manual -> gate satisfied
    assert client.put(f"/api/v1/rfp/packs/{pid}/stage", json={"stage": "final"}, cookies=c).json()["stage"] == "final"


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
            def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
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
            def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
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
