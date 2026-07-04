from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.sources import KnowledgeSources


def _sources():
    return KnowledgeSources(KnowledgeService())


async def test_sources_are_ingested_and_retrievable():
    s = _sources()
    await s.add_behavior("t", "ag", "1", "Always greet the customer politely and stay on brand.")
    await s.add_faq("t", "ag", "1", "Do you hold ISO 9001?", "Yes, valid through 2027.")
    await s.add_policy("t", "ag", "1", "Refund policy", "Refunds within 30 days.")
    await s.add_website("t", "ag", "1", "IDG", "https://idg.example", "Leading provider of audits.")
    await s.set_persona("t", "ag", {"full_name": "IDG Assistant", "expertise": "quality management"})

    assert "ISO 9001" in (await s.knowledge.retrieve("t", "ISO 9001 certification"))[0].text
    assert any("Refund" in p.text for p in await s.knowledge.retrieve("t", "refund policy"))
    assert {d["doc_id"] for d in await s.knowledge.list_documents("t")} == {
        "ag-behavior-1", "ag-faq-1", "ag-policy-1", "ag-website-1", "ag-persona-core"}


async def test_update_reingests_same_doc_id_no_duplicates():
    s = _sources()
    await s.add_behavior("t", "ag", "1", "First version.")
    await s.add_behavior("t", "ag", "1", "Updated version of the behavior.")
    docs = [d for d in await s.knowledge.list_documents("t") if d["doc_id"] == "ag-behavior-1"]
    assert len(docs) == 1  # single doc, re-ingested not duplicated
    assert "Updated version" in (await s.knowledge.retrieve("t", "updated behavior"))[0].text


async def test_delete_source():
    s = _sources()
    await s.add_faq("t", "ag", "9", "Q?", "A.")
    assert await s.delete_source("t", "ag", "faq", "9") >= 1
    assert await s.knowledge.list_documents("t") == []
