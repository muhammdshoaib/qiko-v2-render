"""QIKO-1085: a question whose answer is a whole table must get the whole table.

Found by Jake against real IDG output. A thirteen-row project register spans six 800-character
chunks; retrieval returned some of them, so the answer named nine projects, pulled three more from
neighbouring tables, and asserted the register was absent from the document.
"""
from app.modules.agentcore.critic import grounding_score
from app.modules.knowledge.service import _MAX_WIDENED_CHARS, _WINDOW_RADIUS, KnowledgeService
from app.modules.knowledge.models import Passage
from app.modules.knowledge.store import InMemoryVectorStore

# A table split the way chunking splits one: each row in its own passage, header in the first.
ROWS = [
    "FORM B8-2 CURRENT PROJECTS IN PROGRESS. No. Project Name Location Start Value",
    "1 UNHCR Somalia Somalia 2018 US$1,281,497 p.a.",
    "2 Fly Baghdad Iraq 2024 US$896,400 p.a.",
    "3 Al-Bayan University Iraq 2026 US$285,443 p.a.",
    "4 CTW Iraq 2026 US$177,380 p.a.",
    "5 Asian Development Bank Afghanistan 2012 US$2,325,161 p.a.",
    "6 UNICEF Afghanistan 2010 US$5,987,642 p.a.",
    "7 WFP Afghanistan 2011 US$4,851,899 p.a.",
]


async def _svc(*, agent_id: str | None = "a1", doc_id: str = "tender") -> KnowledgeService:
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", doc_id, "\n\n".join(ROWS), agent_id=agent_id)
    return svc


async def test_a_hit_arrives_with_the_rows_around_it():
    """The defect in one assertion. A query matching one row must not return that row alone."""
    svc = await _svc()
    hits = await svc.retrieve("acme", "Al-Bayan University", k=1, agent_id="a1")
    assert len(hits) == 1
    text = hits[0].text
    # The neighbours either side arrive with it, including the header row.
    for name in ("FORM B8-2", "Fly Baghdad", "Al-Bayan University", "CTW", "UNICEF"):
        assert name in text, name


async def test_the_run_is_merged_into_one_passage_not_several():
    """This is why the fix does not fight QIKO-1086. Grounding requires a sentence to be supported
    by ONE passage, so returning neighbours as separate passages would deliver the table and
    guarantee that any answer summarising it got flagged as ungrounded."""
    svc = await _svc()
    hits = await svc.retrieve("acme", "Al-Bayan University", k=1, agent_id="a1")
    assert len(hits) == 1

    # A sentence drawn from two different rows is grounded, because one passage now holds both.
    summary = "Al-Bayan University in Iraq and Fly Baghdad in Iraq are current projects."
    assert grounding_score(summary, [h.text for h in hits]).grounding == 1.0
    # Against the unmerged rows it would not be: no single row supports it.
    assert grounding_score(summary, ROWS).grounding < 1.0


async def test_overlapping_windows_collapse_into_one_run():
    """Two hits inside the same table must not return the same rows twice."""
    svc = await _svc()
    hits = await svc.retrieve("acme", "Al-Bayan University CTW", k=2, agent_id="a1")
    assert len(hits) == 1, "adjacent hits should have merged into a single run"
    assert hits[0].text.count("Al-Bayan University") == 1


async def test_hits_in_different_documents_stay_separate():
    svc = await _svc()
    await svc.ingest("acme", "other", "Unrelated policy about vehicle maintenance.", agent_id="a1")
    hits = await svc.retrieve("acme", "vehicle maintenance", k=5, agent_id="a1")
    assert {h.doc_id for h in hits} == {"tender", "other"} or {h.doc_id for h in hits} == {"other"}
    for h in hits:
        assert h.doc_id in {"tender", "other"}


async def test_a_tenant_wide_passage_is_widened_with_tenant_wide_neighbours():
    """The trap found while writing this. Unscoped worker retrieval also surfaces legacy
    tenant-wide passages, so widening must match the passage's OWN agent_id, not the caller's
    scope. Filtering on the caller's agent_id dropped tenant-wide runs entirely."""
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "shared", "\n\n".join(ROWS))            # tenant-wide, agent_id None
    hits = await svc.retrieve("acme", "Al-Bayan University", k=1, agent_id="a1")
    assert hits, "a tenant-wide passage must still be retrievable by a worker"
    assert "Fly Baghdad" in hits[0].text


async def test_a_passage_with_no_ordinal_is_returned_untouched():
    """Pre-migration-0050 rows whose ordinal could not be reconstructed keep today's behaviour
    rather than disappearing."""
    store = InMemoryVectorStore()
    await store.add(Passage(id="legacy", tenant="acme", doc_id="old", ordinal=None,
                            text="Legacy passage about ISO 9001 certification.",
                            embedding=[0.0] * 8, agent_id="a1"))
    svc = KnowledgeService(store=store)
    hits = await svc.retrieve("acme", "ISO 9001 certification", k=1, agent_id="a1")
    assert [h.text for h in hits] == ["Legacy passage about ISO 9001 certification."]


async def test_a_merged_run_is_bounded():
    """A pathological document must not swallow an answer's whole context budget."""
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "huge", "\n\n".join(f"row {i} " + "x" * 700 for i in range(40)),
                     agent_id="a1")
    hits = await svc.retrieve("acme", "row 20", k=1, agent_id="a1")
    assert all(len(h.text) <= _MAX_WIDENED_CHARS for h in hits)


async def test_the_window_radius_is_the_measured_one():
    """Pinned because it was chosen from a measurement, not taste. On the IDG KBR submission, for
    the question that exposed the defect, the number of Form B8-2 project names reaching the model
    was 10/12 at radius 3, 12/12 at radius 4, and 12/12 at 5 and 6. Four is the smallest that
    returns the whole register; more only costs context."""
    assert _WINDOW_RADIUS == 4
