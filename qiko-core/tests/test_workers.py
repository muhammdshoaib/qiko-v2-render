from app.modules.agentcore.models import Decision
from app.modules.ai.gateway import StubProvider
from app.modules.knowledge.models import Passage
from app.modules.workers.config import WorkerConfig
from app.modules.workers.registry import WorkerRegistry
from app.modules.workers.worker import build_worker, source_labels

ISO = "IDG holds a current ISO 9001 quality management certification valid through 2027."


def _worker(name="idg", tenant="idg", threshold=0.85):
    cfg = WorkerConfig(name=name, tenant=tenant, gate_threshold=threshold)
    return build_worker(cfg, provider=StubProvider())


def test_config_threshold_propagates():
    w = _worker(threshold=0.9)
    assert w.agent.threshold == 0.9
    assert w.name == "idg"


async def test_ingest_answer_auto_accepts_grounded():
    w = _worker()
    assert await w.ingest("iso-cert", ISO) == 1
    result = await w.answer("B11.1", "Describe your ISO 9001 quality certification.", topic="qms")
    assert result.decision is Decision.auto_accept
    assert result.critique.grounding >= 0.85
    assert "ISO 9001" in result.answer


# --- clean citations: doc_id source labels, not raw passage bodies ---
def test_source_labels_dedupe_by_doc_and_cap_snippet():
    huge = "x" * 5000
    passages = [
        Passage(id="p1", tenant="idg", doc_id="iso-cert.pdf", text=huge),
        Passage(id="p2", tenant="idg", doc_id="iso-cert.pdf", text="another chunk of the same doc"),
        Passage(id="p3", tenant="idg", doc_id="method-statement.docx", text="our method is..."),
    ]
    labels = source_labels(passages)
    # one label per DISTINCT doc_id, order preserved, first occurrence wins
    assert len(labels) == 2
    # just the document name (clean pill), matching the idg cockpit -- not the raw passage body
    assert labels == ["iso-cert.pdf", "method-statement.docx"]
    assert huge not in " ".join(labels)


async def test_answer_citations_are_doc_labels_not_raw_passages():
    w = _worker()
    await w.ingest("iso-cert", ISO)
    result = await w.answer("B11.1", "Describe your ISO 9001 quality certification.", topic="qms")
    assert result.citations  # at least one source
    # citations are labels prefixed by the document id, not the raw passage text
    assert all(c.startswith("iso-cert") for c in result.citations)
    assert len(set(result.citations)) == len(result.citations)  # deduped by doc_id


async def test_answer_with_no_knowledge_escalates():
    w = _worker()
    result = await w.answer("B1", "Describe your ISO 9001 certification.", topic="qms")
    # no evidence retrieved -> stub returns the no-evidence line -> not grounded -> human review
    assert result.decision is Decision.human_review


async def test_approve_feeds_flywheel():
    w = _worker()
    await w.approve("B11.1", ISO, topic="qms")
    assert await w.agent.verified.get("idg", "qms") == [ISO]


async def test_workers_are_tenant_isolated():
    a = _worker(name="idg", tenant="idg")
    b = _worker(name="essential", tenant="essential")
    await a.ingest("d", ISO)
    # worker B has its own tenant + its own knowledge service: sees nothing from A
    assert await b.knowledge.retrieve("essential", "ISO 9001") == []


def test_registry():
    reg = WorkerRegistry()
    reg.register(WorkerConfig(name="idg", tenant="idg"), provider=StubProvider())
    reg.register(WorkerConfig(name="signal", tenant="signal"), provider=StubProvider())
    assert reg.names() == ["idg", "signal"]
    assert reg.get("idg").config.tenant == "idg"
    assert reg.get("missing") is None
