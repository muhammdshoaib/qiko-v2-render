"""Knowledge Base Reference: restricting one tender job's answers to a single document (IDG-1000).

The customer case: IDG submits a large RFP response, the client comes back with a short follow-up
questionnaire about that same submission, and the answers must come from the submitted response
rather than from the whole knowledge base.

The property under test throughout is "no silent fallback": on a scoped job, content from outside
the reference document must never reach an answer, and a question the document cannot support must
come back visibly unanswered rather than quietly answered from elsewhere.
"""
import asyncio
import io
import json

from app.modules.agentcore.generator import Generator
from app.modules.agents.service import Agent
from app.modules.ai.gateway import LLMResponse
from app.modules.rfp import generation

from tests.helpers import auth_cookies

BID = ("IDG delivered armed and unarmed guarding for the UNAMA compound under contract 42, "
       "with a 24-hour control room and monthly KPI reporting.")
HSE = ("The corporate health and safety policy covers site risk assessments, incident reporting "
       "and annual refresher training for all deployed personnel.")

def _req_json(requirement="Describe your experience providing guarding at the UNAMA compound."):
    """The extraction step is canned, so the REQUIREMENT text a test wants answered has to be set
    here rather than in the uploaded bytes -- the upload is only ever fed to extraction."""
    return json.dumps([
        {"id": "A1", "title": "Question", "classification": "KB", "requirement": requirement},
    ])


REQ_JSON = _req_json()
BRIEF_JSON = json.dumps({
    "summary": "Follow-up questionnaire.", "scope": "Summary of the submitted response.",
    "submission_format": "Email.", "key_dates": [], "success_criteria": [], "gaps_and_risks": [],
})
COMPLIANCE_JSON = json.dumps([])


class _EchoProvider:
    """Answers extraction/brief/compliance from canned JSON, and echoes the retrieved CONTEXT for
    everything else, so an answer can be inspected for content that came from outside the scope."""

    def __init__(self, req_json: str = REQ_JSON, answer: str | None = None):
        self.req_json = req_json
        # When set, the draft is this text instead of the echoed evidence. Echoing makes the
        # answer perfectly grounded by construction, so an ungrounded draft is the only way to
        # exercise the critic and the gate.
        self.answer = answer

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        s = (system or "").lower()
        if "compliance analyst" in s:
            return LLMResponse(text=COMPLIANCE_JSON)
        if "bid manager" in s:
            return LLMResponse(text=BRIEF_JSON)
        if "requirement" in s or "extract" in s:
            return LLMResponse(text=self.req_json)
        if self.answer is not None:
            return LLMResponse(text=json.dumps(
                {"answer": self.answer, "confidence": 0.9, "gaps": ""}))
        context = ""
        if "CONTEXT:" in prompt:
            context = prompt.split("CONTEXT:", 1)[1].split("REQUIREMENT:", 1)[0].strip()
        return LLMResponse(text=json.dumps(
            {"answer": context or "no evidence", "confidence": 0.9, "gaps": ""}))


def _seed(client, tenant, *, docs=(("bid-2024", BID), ("hse-policy", HSE))):
    """A worker with a two-document knowledge base: one the follow-up relates to, one it does not."""
    async def go():
        await client.app.state.agents.store.add(Agent(id="w1", tenant=tenant, name="Worker"))
        for doc_id, text in docs:
            await client.app.state.knowledge.ingest(tenant, doc_id, text, agent_id="w1")
    asyncio.run(go())
    c = auth_cookies(tenant, "owner")
    pid = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Follow-up"},
                      cookies=c).json()["id"]
    return c, pid


def _upload(client, c, pid, *, reference_doc_id=None, body=b"Question 1: describe UNAMA guarding."):
    data = {"reference_doc_id": reference_doc_id} if reference_doc_id is not None else None
    return client.post(f"/api/v1/rfp/packs/{pid}/extract", cookies=c, data=data,
                       files={"file": ("q.txt", io.BytesIO(body), "text/plain")})


def _patch(monkeypatch, *, requirement=None, answer=None):
    # Three distinct symbols, all bound at import time, so patching the gateway module alone
    # leaves the others talking to real Bedrock: the background pipelines use the one in
    # rfp.generation, a Worker's Generator the one in agentcore.generator, and the cockpit chat
    # the one in rfp.router.
    #
    # The names differ because QIKO-1081 split the document-scale calls out into
    # `document_provider`, which raises the read timeout and the output token ceiling together.
    # rfp.generation and rfp.router moved to it; agentcore.generator is a hot-path caller and
    # still binds `get_provider`. Patch whichever name each module actually holds, or the stub
    # silently misses and the test hits Bedrock for real.
    req_json = _req_json(requirement) if requirement else REQ_JSON

    def provider(**_kw):
        return _EchoProvider(req_json, answer)

    monkeypatch.setattr(generation, "document_provider", provider)
    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", provider)
    monkeypatch.setattr("app.modules.rfp.router.document_provider", provider)


# --- persistence and the lock ------------------------------------------------------------------
def test_reference_doc_is_recorded_on_the_pack(client, monkeypatch):
    _patch(monkeypatch)
    c, pid = _seed(client, "refrec")
    assert _upload(client, c, pid, reference_doc_id="bid-2024").status_code == 202
    assert client.get(f"/api/v1/rfp/packs/{pid}", cookies=c).json()["reference_doc_id"] == "bid-2024"


def test_upload_without_a_reference_is_unscoped(client, monkeypatch):
    """The default path. Absence must be visible as an explicit null, so the job screen can say
    "full knowledge base" rather than leaving a reviewer guessing."""
    _patch(monkeypatch)
    c, pid = _seed(client, "refnone")
    assert _upload(client, c, pid).status_code == 202
    assert client.get(f"/api/v1/rfp/packs/{pid}", cookies=c).json()["reference_doc_id"] is None


def test_unknown_reference_is_rejected_and_nothing_is_started(client, monkeypatch):
    """Fails closed. Accepting an unknown id would scope the job to nothing and flag every question
    as unanswerable, which reads as the product being broken rather than as a bad input."""
    _patch(monkeypatch)
    c, pid = _seed(client, "refbad")
    r = _upload(client, c, pid, reference_doc_id="no-such-document")
    assert r.status_code == 422
    pack = client.get(f"/api/v1/rfp/packs/{pid}", cookies=c).json()
    assert pack["reference_doc_id"] is None
    assert client.get(f"/api/v1/rfp/packs/{pid}/status", cookies=c).json() == {}


def test_another_tenants_document_cannot_be_named_as_a_reference(client, monkeypatch):
    _patch(monkeypatch)
    _seed(client, "refvictim", docs=(("secret-bid", "Victim confidential pricing."),))
    c, pid = _seed(client, "refattacker")
    assert _upload(client, c, pid, reference_doc_id="secret-bid").status_code == 422


def test_a_second_upload_may_set_a_different_reference(client, monkeypatch):
    """"Re-scoping requires a new upload": the scope is not editable in place, but a fresh upload
    establishes a new one, and dropping it clears the old one rather than inheriting it."""
    _patch(monkeypatch)
    c, pid = _seed(client, "refreup")
    _upload(client, c, pid, reference_doc_id="bid-2024")
    _upload(client, c, pid, reference_doc_id="hse-policy")
    assert client.get(f"/api/v1/rfp/packs/{pid}", cookies=c).json()["reference_doc_id"] == "hse-policy"
    _upload(client, c, pid)
    assert client.get(f"/api/v1/rfp/packs/{pid}", cookies=c).json()["reference_doc_id"] is None


def test_no_endpoint_edits_the_reference_on_an_existing_job(client):
    """Guards the "locked for the life of the job" criterion against a future endpoint being added
    without anyone noticing it reopens the scope."""
    paths = {route.path for route in client.app.routes}
    assert not [p for p in paths if "reference" in p.lower()]


# --- the scope actually applies ------------------------------------------------------------------
def test_scoped_job_drafts_only_from_the_reference_document(client, monkeypatch):
    _patch(monkeypatch)
    c, pid = _seed(client, "refscoped")
    _upload(client, c, pid, reference_doc_id="bid-2024")

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    question = tree[0]["questions"][0]
    assert question["ai_sources"] == ["bid-2024"]
    # The echo provider returns the retrieved evidence verbatim, so the health and safety document
    # appearing in the answer would prove a fallback happened.
    assert "health and safety policy" not in question["ai_answer"]


def test_unscoped_job_still_reaches_the_whole_knowledge_base(client, monkeypatch):
    """The regression that matters most: every existing tender must behave exactly as before."""
    # The same question that comes back unanswerable when scoped to the bid document below must
    # still be answered here, from the wider knowledge base.
    _patch(monkeypatch,
           requirement="Describe your annual refresher training for deployed personnel.")
    c, pid = _seed(client, "refunscoped")
    _upload(client, c, pid)

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    # Ranked first because it is the document that answers the question; the bid document may also
    # appear, since BM25 scores any shared word and applies no stopword list.
    assert tree[0]["questions"][0]["ai_sources"][0] == "hse-policy"


def test_a_question_the_reference_cannot_support_is_flagged_not_answered(client, monkeypatch):
    """IDG-1003. The bid document says nothing about training, so the question must come back
    flagged as a KB gap with a note naming the document, and must NOT be answered from the health
    and safety policy that does cover it.

    Note what is and is not asserted. The document is still cited: BM25 applies no stopword list,
    so a shared common word pulls back weak passages. That is the ordinary case on a scoped job,
    and the gate escalating on low grounding is what makes it visible -- which is exactly why the
    gaps note keys on "unsupported", not on "no citations"."""
    _patch(monkeypatch,
           requirement="Describe your annual refresher training for deployed personnel.",
           # The model answers from general knowledge, which the reference document does not
           # support. The critic scores it ungrounded and the gate escalates: the realistic
           # shape of this failure, and the one the note has to cover.
           answer="All personnel complete annual refresher training certified to ISO 18788.")
    c, pid = _seed(client, "refgap")
    _upload(client, c, pid, reference_doc_id="bid-2024")

    tree = client.get(f"/api/v1/rfp/packs/{pid}/sections", cookies=c).json()
    question = tree[0]["questions"][0]
    assert "hse-policy" not in question["ai_sources"]  # no fallback to the document that answers it
    assert question["kb_gap"] is True
    assert question["decision"] == "human_review"
    assert "bid-2024" in question["gaps"]
    assert "does not contain enough detail" in question["gaps"]
    # The ungrounded draft is still stored -- that is what human_review is for. What matters is
    # that it is never presented as accepted, and that the reason names the reference document.
    assert question["grounding"] < 0.85


def test_cockpit_chat_is_scoped_too(client, monkeypatch):
    """Confirmed with Jake: the answer-development chat feeds the same submission, so it must not
    be a way around the scope."""
    _patch(monkeypatch)
    c, pid = _seed(client, "refchat")
    _upload(client, c, pid, reference_doc_id="bid-2024")

    answer = client.post(f"/api/v1/rfp/packs/{pid}/chat", cookies=c,
                         json={"question": "What does our health and safety policy cover?"}).json()
    assert "annual refresher training" not in answer["answer"]


# --- the prompt tells the truth about why it cannot answer ---------------------------------------
def test_scoped_prompt_forbids_outside_sources_and_names_the_limit():
    scoped = Generator(provider=_EchoProvider(), reference_scoped=True).system
    assert "only permitted source" in scoped
    assert "does not contain enough detail" in scoped


def test_no_prompt_claims_the_knowledge_base_is_empty():
    """The pre-existing defect this feature would otherwise have made routine: telling a customer
    with a full knowledge base that nothing has been uploaded."""
    for generator in (Generator(provider=_EchoProvider()),
                      Generator(provider=_EchoProvider(), reference_scoped=True),
                      Generator(provider=_EchoProvider(), system_prompt="You are IDG's bid writer.")):
        assert "no knowledge base has been uploaded" not in generator.system


def test_the_scope_constraint_survives_a_worker_persona():
    """The IDG pre-sales worker has a synthesized persona (QIK-315), which replaces the default
    identity entirely. The scope constraint is layered separately precisely so it is not lost for
    the workers this feature exists for."""
    generator = Generator(provider=_EchoProvider(), reference_scoped=True,
                          system_prompt="You are IDG's bid writer.")
    assert "You are IDG's bid writer." in generator.system
    assert "only permitted source" in generator.system


def test_unscoped_prompt_is_byte_identical_to_before():
    from app.modules.agentcore.generator import SYSTEM

    assert Generator(provider=_EchoProvider()).system == SYSTEM
