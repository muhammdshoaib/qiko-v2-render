import io

from app.modules.knowledge.service import KnowledgeService


def _docx(text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def test_ingest_file_list_and_delete_cascade():
    svc = KnowledgeService()
    await svc.ingest_file("acme", "iso-cert", "iso.docx", _docx("IDG holds ISO 9001 certification."))
    await svc.ingest_file("acme", "hse-policy", "hse.txt", b"Health and safety policy details.")

    # both documents listed with chunk counts
    docs = {d["doc_id"]: d["chunks"] for d in await svc.list_documents("acme")}
    assert set(docs) == {"iso-cert", "hse-policy"} and all(c >= 1 for c in docs.values())

    # retrievable
    assert "ISO 9001" in (await svc.retrieve("acme", "ISO 9001 certification"))[0].text

    # delete cascades: doc gone, other remains
    removed = await svc.delete_document("acme", "iso-cert")
    assert removed >= 1
    assert [d["doc_id"] for d in await svc.list_documents("acme")] == ["hse-policy"]
    assert all("ISO 9001" not in p.text for p in await svc.retrieve("acme", "ISO 9001"))


async def test_delete_missing_document_is_noop():
    svc = KnowledgeService()
    assert await svc.delete_document("acme", "nope") == 0
