"""RFP pack HTTP API (tenant-scoped): create/list/get/delete tenders a worker is answering."""
from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.deps import (
    WorkerRecheck,
    authed_tenant,
    current_claims,
    get_chat,
    get_pack_answers,
    get_pack_tree,
    get_requirements,
    get_rfp_packs,
    get_teams_notifier,
    get_user_store,
    require_available_worker,
    require_role,
    resolve_tenant_worker,
)
from app.modules.ai.gateway import document_provider
from app.modules.chat.files import build_docx, build_xlsx
from app.modules.identity.rbac import Role, role_allows
from app.modules.knowledge.parsing import MAX_UPLOAD_BYTES, UnsupportedDocumentError, extract_text
from app.modules.rfp.brief import BriefError, extract_brief
from app.modules.rfp.compliance import ComplianceError, extract_compliance
from app.modules.rfp.generation import (
    StubProviderUnavailable,
    generate_question as generate_question_core,
    initial_gen_status,
)
from app.modules.rfp.scoring import ScoringError, score_opportunity
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.rfp.service import MAX_OUTCOME_VALUE, PackRequirement, RfpPack, RfpPackNotFound
from app.modules.rfp.tree import PackQuestionNotFound, PackSection, PackSectionNotFound
from app.modules.workers.worker import source_labels
from app.tasks.queue import EagerTaskQueue

router = APIRouter(prefix="/rfp/packs", tags=["rfp"])

# extract/ask/compliance/brief are one-shot calls over a whole tender document (tens of thousands
# of chars in, a full structured response out) -- the gateway's default read_timeout (20s) is
# tuned for the fast per-requirement answering hot path and is routinely too tight for these.
_DOCUMENT_READ_TIMEOUT = 90


async def _resolve_pack_worker(request: Request, tenant: str, pack_id: str, packs):
    """Every answer-producing path in this module goes through here, which is what makes the
    Knowledge Base Reference (IDG-1000) apply uniformly: the pack's own reference_doc_id is bound
    into the Worker, so per-question, per-section, whole-pack and regenerate-all are all scoped
    without each call site having to remember. The background drafts job does the same in
    rfp.generation.run_generation, and /chat retrieves directly so it passes doc_id itself."""
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    worker, recheck = await resolve_tenant_worker(
        request, tenant, pack.agent_id, reference_doc_id=pack.reference_doc_id)
    return pack, worker, recheck


async def _validated_reference_doc(request: Request, tenant: str, agent_id: str,
                                   reference_doc_id: str | None) -> str | None:
    """Resolve the requested Knowledge Base Reference to a document the caller's worker actually
    holds, or 422.

    Fails closed on purpose. An unknown id would otherwise scope the job to nothing, every
    question would come back flagged as unanswerable, and that reads as the product being broken
    rather than as a bad input. list_documents is already tenant- and agent-scoped, so this is
    also what stops one tenant naming another's document."""
    doc_id = (reference_doc_id or "").strip()
    if not doc_id:
        return None
    known = await request.app.state.knowledge.list_documents(tenant, agent_id=agent_id)
    if doc_id not in {d["doc_id"] for d in known}:
        raise HTTPException(
            status_code=422,
            detail="that knowledge base reference is not a document this worker can use")
    return doc_id


async def _resolve_pack(request: Request, tenant: str, pack_id: str, packs):
    pack, _worker, recheck = await _resolve_pack_worker(request, tenant, pack_id, packs)
    return pack, recheck


class CreatePackBody(BaseModel):
    agent_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    client_name: str = ""
    deadline: str | None = None


@router.post("")
async def create_pack(body: CreatePackBody, request: Request,
                      tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)),
                      svc=Depends(get_rfp_packs)) -> RfpPack:
    await require_available_worker(
        agents=request.app.state.agents, tenant=tenant, agent_id=body.agent_id)
    return await svc.create(tenant, body.agent_id, body.title,
                            client_name=body.client_name, deadline=body.deadline)


@router.get("")
async def list_packs(agent_id: str | None = None, tenant: str = Depends(authed_tenant),
                     svc=Depends(get_rfp_packs)) -> list[RfpPack]:
    return await svc.list(tenant, agent_id=agent_id)


@router.get("/stats")
async def pack_stats(agent_id: str | None = None, tenant: str = Depends(authed_tenant),
                     svc=Depends(get_rfp_packs)) -> dict:
    """Win/Loss Analysis rollup (see RfpPackService.stats) -- registered before /{pack_id} so the
    literal 'stats' path segment can never be swallowed as a pack_id."""
    return await svc.stats(tenant, agent_id=agent_id)


@router.get("/{pack_id}")
async def get_pack(pack_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_rfp_packs)) -> RfpPack:
    try:
        return await svc.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e


class StageBody(BaseModel):
    stage: str


@router.put("/{pack_id}/stage")
async def set_stage(pack_id: str, body: StageBody, request: Request,
                    claims: dict = Depends(current_claims),
                    tenant: str = Depends(authed_tenant),
                    _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs),
                    tree=Depends(get_pack_tree)) -> RfpPack:
    """Move the pack through its stages. "final" is the submission point.

    Audited because reaching "final" is the roll-up of every section lock: it is the moment the pack
    stopped being a draft, and the guard below is what stops it happening without review sign-off.
    """
    pack, recheck = await _resolve_pack(request, tenant, pack_id, svc)
    # A pack can only be finalised once every section is locked (lock roll-up governance) -- guard
    # here so the generic stage transition can't skip review sign-off.
    if body.stage == "final" and not await tree.all_sections_locked(tenant, pack_id):
        raise HTTPException(status_code=409, detail="cannot finalise: every section must be locked first")
    try:
        await recheck()
        # Captured before the mutation for the same reason as the locks above.
        previous = getattr(pack, "stage", None)
        updated = await svc.set_stage(tenant, pack_id, body.stage)
        if previous != body.stage:
            await _record_governance(
                request, audit_actions.PACK_STAGE_CHANGED, tenant, claims,
                target_id=pack_id, pack_id=pack_id,
                before={"stage": previous}, after={"stage": body.stage},
                # Recorded on the row itself: months later, "was review actually complete when this was
                # finalised" is answerable from the audit rather than from the pack's current state,
                # which by then has moved on.
                metadata={"title": getattr(pack, "title", None),
                          "finalised": body.stage == "final"})
        return updated
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


class OutcomeBody(BaseModel):
    outcome: str | None = None  # "won" | "lost" | "withdrawn" | null to clear
    reason: str = ""  # loss reason, one of rfp.service.LOSS_REASONS -- only meaningful when lost
    value: float | None = Field(default=None, ge=0, le=MAX_OUTCOME_VALUE)


@router.put("/{pack_id}/outcome")
async def set_outcome(pack_id: str, body: OutcomeBody, request: Request,
                      claims: dict = Depends(current_claims),
                      tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs),
                      notifier=Depends(get_teams_notifier)) -> RfpPack:
    """Win/Loss Analysis: record what happened to a submitted tender. Feeds /rfp/packs/stats."""
    persisted, recheck = await _resolve_pack(request, tenant, pack_id, svc)
    # Read off the live row before the mutation, or it reports the value just written.
    previous_outcome = getattr(persisted, "outcome", None)
    try:
        pack = await svc.set_outcome_for_enabled_agent(
            tenant, pack_id, persisted.agent_id, outcome=body.outcome,
            reason=body.reason, value=body.value, recheck_worker=recheck)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # Feeds /rfp/packs/stats, so its integrity is commercial rather than merely operational: a win rate
    # nobody can attribute is a number a bid team reports and cannot defend.
    await _record_governance(
        request, audit_actions.PACK_OUTCOME_RECORDED, tenant, claims,
        target_id=pack_id, pack_id=pack_id,
        before={"outcome": previous_outcome},
        after={"outcome": body.outcome, "reason": body.reason or None, "value": body.value},
        metadata={"title": getattr(pack, "title", None)})
    if body.outcome == "won":
        await notifier.notify(tenant, f"\U0001f389 Tender won: **{pack.title}**"
                              + (f" (${body.value:,.0f})" if body.value else ""))
    elif body.outcome == "lost":
        await notifier.notify(tenant, f"Tender lost: **{pack.title}**"
                              + (f" -- reason: {body.reason}" if body.reason else ""))
    return pack


@router.delete("/{pack_id}")
async def delete_pack(pack_id: str, request: Request,
                      claims: dict = Depends(current_claims),
                      tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs),
                      reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                      tree=Depends(get_pack_tree)) -> dict:
    pack, recheck = await _resolve_pack(request, tenant, pack_id, svc)
    await recheck()
    # Counted before the cascade, because afterwards there is nothing left to count. A tender pack is
    # weeks of a bid team's work across four tables and this endpoint removes all of it with no undo,
    # so the size of what was destroyed is the substance of the record.
    #
    # An earlier version called tree.sections_for_pack behind a hasattr guard. No such method exists,
    # so the guard was always false and every row recorded sections: 0. A fabricated zero is worse than
    # an absent field: it reads as evidence that nothing was there.
    sections = await tree.sections.list(tenant, pack_id)
    questions = await tree.questions.list(tenant, pack_id)
    counts = {"sections": len(sections), "questions": len(questions)}
    await answers.delete_for_pack(tenant, pack_id)
    await recheck()
    await reqs.delete_for_pack(tenant, pack_id)
    await recheck()
    await tree.delete_for_pack(tenant, pack_id)
    await recheck()
    await svc.delete(tenant, pack_id)
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.RFP_PACK_DELETED, target_id=pack_id,
        target_label=getattr(pack, "title", None), tenant_id=tenant, actor_type=audit.USER,
        actor_id=str(claims.get("sub") or ""), actor_label=str(claims.get("email") or ""),
        reason=request.headers.get("x-audit-reason"),
        changes=audit.diff(audit_actions.RFP_PACK_DELETED, {}, counts),
        metadata={"cascaded": ["answers", "requirements", "sections", "questions", "pack"]}),
        request=request)
    return {"deleted": pack_id}


async def _start_generation(request: Request, tenant: str, pack_id: str, text: str, packs,
                            reqs, answers, tree, *, agent_id: str,
                            recheck: WorkerRecheck,
                            reference_doc_id: str | None = None) -> dict:
    """Persist the uploaded tender text, mark every artifact pending, and kick off the background
    job that produces requirements/sections/brief/compliance/drafts -- then return immediately so
    the upload doesn't block on a full generation pass. The frontend polls GET .../status.

    The Eager queue backend (dev/tests) runs the job inline against these SAME in-memory stores, so
    everything is populated by the time this returns; the arq backend (prod) enqueues onto Redis
    for the worker tier, which rebuilds the stores from its own DB sessionmaker -- so only the
    serializable ids are put on the wire in that case."""
    await recheck()
    await packs.set_document_text(tenant, pack_id, text)
    await recheck()
    # Written BEFORE the job is enqueued, and written even when it is None, so the eager and arq
    # backends both read the same scope and a re-upload without a reference clears a previous one
    # instead of silently inheriting it.
    await packs.set_reference_doc(tenant, pack_id, reference_doc_id)
    await recheck()
    await packs.set_gen_status(tenant, pack_id, initial_gen_status())
    await recheck()
    task_queue = request.app.state.task_queue
    if isinstance(task_queue, EagerTaskQueue):
        await task_queue.enqueue("generate_tender_artifacts", tenant=tenant, pack_id=pack_id,
                                 agent_id=agent_id, packs=packs, reqs=reqs, answers=answers,
                                 tree=tree, knowledge=request.app.state.knowledge,
                                 agents=request.app.state.agents)
    else:  # pragma: no cover - arq prod path (Redis carries only the serializable ids)
        await task_queue.enqueue("generate_tender_artifacts", tenant=tenant, pack_id=pack_id,
                                 agent_id=agent_id)
    return {"status": "processing", "pack_id": pack_id}


@router.post("/{pack_id}/extract", status_code=202)
async def extract(pack_id: str, request: Request,
                  files: list[UploadFile] | None = File(default=None),
                  file: UploadFile | None = File(default=None),
                  # Bounded here, before _validated_reference_doc reads the corpus to check it, so
                  # an oversized value is rejected without that read. Matches Passage.doc_id.
                  reference_doc_id: str | None = Form(default=None, max_length=128),
                  tenant: str = Depends(authed_tenant),
                  _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs),
                  reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                  tree=Depends(get_pack_tree)) -> dict:
    """Upload one OR MANY RFP/tender documents and kick off BACKGROUND generation of every artifact
    (requirements, sections, brief, compliance, per-section drafts). Every readable file's text is
    combined into one document (each under a `===== DOCUMENT: <name> =====` header) so downstream
    extraction/brief/compliance/chat see the whole document set, and one source_documents entry is
    recorded per file so the cockpit can show what went in. Returns immediately with
    {"status": "processing"}; poll GET /rfp/packs/{id}/status for per-artifact progress.

    Optionally scoped: `reference_doc_id` restricts this job's answers to that ONE knowledge base
    document, with no fallback to the wider corpus (IDG-1000). Omitting it keeps today's behaviour
    exactly. The scope is fixed here and never edited afterwards, so re-scoping means a new upload.

    Backward compatible: accepts many files under the `files` field, and also a single legacy
    `file` field, so an older single-file client still works."""
    pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    # Validated before anything is persisted, so a bad reference fails the upload outright rather
    # than producing a job whose every answer is silently unanswerable.
    reference = await _validated_reference_doc(request, tenant, pack.agent_id, reference_doc_id)

    uploads: list[UploadFile] = list(files or [])
    if file is not None:
        uploads.append(file)
    if not uploads:
        raise HTTPException(status_code=422, detail="no files uploaded")

    uploaded_at = datetime.now(timezone.utc).isoformat()
    parts: list[str] = []
    source_documents: list[dict] = []
    last_error: str | None = None
    for f in uploads:
        # Read with a hard cap PER FILE so a huge upload can't exhaust memory (defence beyond the
        # global request-size middleware), mirroring finance.router.upload.
        data = await f.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file exceeds the 10MB limit")
        name = f.filename or "document.txt"
        try:
            text = extract_text(name, data)
        except UnsupportedDocumentError as e:
            last_error = str(e)  # skip this one; only fail the request if EVERY file fails
            continue
        parts.append(f"===== DOCUMENT: {name} =====\n{text}")
        source_documents.append({"name": name, "chars": len(text), "uploaded_at": uploaded_at})

    if not source_documents:
        raise HTTPException(status_code=422, detail=last_error or "no readable documents uploaded")

    # Record the source set on a dedicated field (survives the gen_status reset in
    # _start_generation) before kicking off generation over the combined text.
    await recheck()
    await packs.set_source_documents(tenant, pack_id, source_documents)
    return await _start_generation(request, tenant, pack_id, "\n\n".join(parts), packs, reqs,
                                   answers, tree, agent_id=pack.agent_id, recheck=recheck,
                                   reference_doc_id=reference)


class ExtractUrlBody(BaseModel):
    url: str = Field(min_length=1, pattern=r"^https?://")
    # Same optional Knowledge Base Reference as /extract, so a tender sourced from a URL can be
    # scoped identically to an uploaded one.
    reference_doc_id: str | None = Field(default=None, max_length=128)


def _assert_public_url(url: str) -> None:
    """Basic SSRF guard (OWASP A10/API7): this URL is fetched server-side on an editor's say-so,
    so it must not be usable to probe internal infrastructure -- loopback, private/link-local
    ranges, and the cloud metadata endpoint are all rejected. Not exhaustive (DNS rebinding after
    this check is a known residual risk of any hostname-based allowlist), but redirects are
    disabled below specifically so a validated URL can't be used to hop to a disallowed one."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    host = urlparse(url).hostname
    if not host:
        raise HTTPException(status_code=422, detail="invalid URL")
    try:
        addr = socket.gethostbyname(host)
        ip = ipaddress.ip_address(addr)
    except (socket.gaierror, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"could not resolve host: {e}") from e
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        raise HTTPException(status_code=422, detail="that URL points to a non-public address, which is not allowed")


@router.post("/{pack_id}/extract-url", status_code=202)
async def extract_from_url(pack_id: str, body: ExtractUrlBody, request: Request,
                           tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs),
                           reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                           tree=Depends(get_pack_tree)) -> dict:
    """Same as /extract, but sourced from a tender published on a webpage instead of an uploaded
    file -- fetches the URL, extracts its text (HTML or a direct PDF/DOCX link both work, since
    extract_text dispatches on the response's actual content type), then kicks off the same
    BACKGROUND generation job. Returns immediately with {"status": "processing"}."""
    pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    reference = await _validated_reference_doc(
        request, tenant, pack.agent_id, body.reference_doc_id)

    import httpx

    _assert_public_url(body.url)
    try:
        await recheck()
        # Redirects deliberately NOT followed -- a redirect target skips the public-address
        # check above, which would defeat it.
        resp = await asyncio.to_thread(httpx.get, body.url, timeout=20.0, follow_redirects=False,
                                       headers={"User-Agent": "Mozilla/5.0 (compatible; QikoBot/1.0)"})
        await recheck()
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=422, detail=f"could not fetch that URL: {e}") from e

    content_type = resp.headers.get("content-type", "")
    filename = ("page.pdf" if "pdf" in content_type else "page.docx" if "officedocument" in content_type
               else "page.html" if "html" in content_type or not content_type else (body.url.rsplit("/", 1)[-1] or "page.html"))
    try:
        text = extract_text(filename, resp.content)
    except UnsupportedDocumentError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if not text.strip():
        raise HTTPException(status_code=422, detail="that URL had no extractable text")

    return await _start_generation(request, tenant, pack_id, text, packs, reqs, answers, tree,
                                   agent_id=pack.agent_id, recheck=recheck,
                                   reference_doc_id=reference)


class AskBody(BaseModel):
    question: str = Field(min_length=1)


@router.post("/{pack_id}/ask")
async def ask_bid_context(pack_id: str, body: AskBody, request: Request,
                          tenant: str = Depends(authed_tenant),
                          packs=Depends(get_rfp_packs)) -> dict:
    """Bid Context Q&A: answer ad-hoc questions about the tender itself (scope, rules, format,
    deadlines, risks) grounded ONLY in the uploaded tender document -- distinct from the
    requirement-answering flow, which draws on the tenant's knowledge base instead. Port of
    idg-worker's app/agents/bid_context.py."""
    pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    if not pack.document_text:
        raise HTTPException(status_code=422, detail="no tender document on file for this pack -- run /extract first")

    system = ("You are a tender analyst. Answer questions about THIS tender using ONLY the tender "
             "document provided. Be precise about scope, submission format, deadlines, "
             "qualification rules and risks. If the document doesn't state it, say so -- do not guess.")
    prompt = f"TENDER DOCUMENT:\n{pack.document_text[:60_000]}\n\nQUESTION: {body.question}\n\nAnswer from the document only."
    await recheck()
    response = await asyncio.to_thread(document_provider(read_timeout=_DOCUMENT_READ_TIMEOUT).generate,
                                       prompt, system=system, temperature=0.0)
    await recheck()
    return {"question": body.question, "answer": response.text}


def _tender_conversation_id(pack_id: str) -> str:
    """Deterministic, per-pack conversation id so a tender's cockpit chat maps to exactly one stored
    conversation (tenant-scoped in the chat store). Reused by both the POST /chat write path and the
    GET /chat/history read path so reopening/refreshing the cockpit shows the prior exchange."""
    return f"tender:{pack_id}"


# The per-tender cockpit chat can accumulate many turns over a bid's lifecycle; return a generous
# window (well beyond the general chat's HISTORY_WINDOW) so reopening shows the full conversation.
_TENDER_HISTORY_LIMIT = 500


@router.post("/{pack_id}/chat")
async def tender_chat(pack_id: str, body: AskBody, request: Request,
                      tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)),
                      packs=Depends(get_rfp_packs), chat=Depends(get_chat)) -> dict:
    """Answer-development chat for a tender. Grounds in BOTH this tender (brief, key dates and an
    extract of the tender document, so it answers deadline/scope/rules questions) AND the tenant's
    KNOWLEDGE BASE (so it can develop and expand answers from company documents, for example 'when
    was our HR system developed and how secure is it'). Cited; says so plainly only when the answer
    is in neither the tender nor the knowledge base, and never invents facts.

    Each exchange is persisted to a per-pack conversation (reusing the general ChatService store, so
    it is Postgres-backed under USE_DB_STORES and survives close/refresh/logout), which GET
    /rfp/packs/{id}/chat/history reads back in order."""
    pack, worker, recheck = await _resolve_pack_worker(request, tenant, pack_id, packs)
    await recheck()
    # Scoped like every other answer on a scoped job (IDG-1000): the cockpit chat develops the
    # answers that go into the same submission, so letting it read the wider knowledge base would
    # reintroduce exactly the inconsistency the reference document exists to prevent.
    passages = await worker.knowledge.retrieve(tenant, body.question, k=worker.config.retrieval_k,
                                               agent_id=worker.config.agent_id,
                                               doc_id=pack.reference_doc_id)
    await recheck()
    no_kb_match = ("(the reference document for this tender contains nothing relevant)"
                   if pack.reference_doc_id else "(no matching company documents)")
    kb_block = "\n\n".join(f"[{i + 1}] {p.text}" for i, p in enumerate(passages)) or no_kb_match

    # Tender context must answer TENDER questions (deadline, scope, submission rules, key dates), so
    # include the whole brief (summary/scope/format/key_dates/etc.) AND a generous slice of the
    # tender document itself -- the closing date lives on page 1 of the RFP, not in the brief summary.
    brief = pack.brief or {}
    ctx = [f"Tender: {pack.title}"]
    if pack.deadline:
        ctx.append(f"Submission deadline (from the tender record): {pack.deadline}")
    for key, label in (("summary", "Summary"), ("scope", "Scope"),
                       ("submission_format", "Submission format"), ("success_criteria", "Success criteria"),
                       ("gaps_and_risks", "Gaps and risks")):
        val = brief.get(key)
        if val:
            ctx.append(f"{label}: {val}")
    if brief.get("key_dates"):
        dates = brief["key_dates"]
        dates_txt = "\n".join(f"- {d}" for d in dates) if isinstance(dates, list) else str(dates)
        ctx.append(f"Key dates:\n{dates_txt}")
    if pack.document_text:
        ctx.append("Tender document (extract):\n" + pack.document_text[:24_000])
    tender_ctx = "\n".join(ctx)

    system = ("You are a bid-writing assistant helping develop a tender response. You are given the "
              "TENDER CONTEXT (this tender's brief, key dates and an extract of the tender document) "
              "and the COMPANY KNOWLEDGE BASE. Answer questions about THIS TENDER (deadlines, scope, "
              "submission rules, key dates, requirements) from the TENDER CONTEXT, and questions "
              "about the company (capabilities, systems, certifications, past performance, security "
              "posture) from the KNOWLEDGE BASE, using both together to develop and expand answers. "
              "Be specific and cite what you rely on. Only say you cannot find something if it is "
              "genuinely in neither the tender context nor the knowledge base, and never invent facts.")
    prompt = (f"TENDER CONTEXT:\n{tender_ctx}\n\nCOMPANY KNOWLEDGE BASE:\n{kb_block}\n\n"
              f"QUESTION: {body.question}\n\nAnswer, grounded in the above.")
    await recheck()
    response = await asyncio.to_thread(document_provider(read_timeout=_DOCUMENT_READ_TIMEOUT).generate,
                                       prompt, system=system, temperature=0.2)
    await recheck()
    # Fail closed: never surface StubProvider echo text as a real answer during a provider outage.
    if response.stub:
        raise StubProviderUnavailable()

    # Persist both turns so the conversation survives close/refresh/logout. Written only after a
    # real answer (the stub-outage path above short-circuits first), user turn before assistant so
    # they read back in order. The store is the SAME one the general chat uses, so under
    # USE_DB_STORES this is Postgres-backed rather than in-memory.
    cid = _tender_conversation_id(pack_id)
    await chat.store.append_exchange_for_enabled_agent(
        tenant, cid, user_id="public", agent_id=pack.agent_id, crm_eligible=False,
        user_text=body.question, assistant_text=response.text, recheck_worker=recheck)
    await recheck()
    return {"question": body.question, "answer": response.text, "sources": source_labels(passages)}


@router.get("/{pack_id}/chat/history")
async def tender_chat_history(pack_id: str, tenant: str = Depends(authed_tenant),
                              packs=Depends(get_rfp_packs), chat=Depends(get_chat)) -> list[dict]:
    """Stored per-tender cockpit chat, in order, so reopening/refreshing the cockpit restores the
    conversation. Tenant-scoped and 404 for an unknown or cross-tenant pack (the pack lookup is
    itself tenant-scoped). Viewer-readable, matching the general GET /chat/history read path."""
    try:
        await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    msgs = await chat.history(tenant, _tender_conversation_id(pack_id), limit=_TENDER_HISTORY_LIMIT)
    return [{"role": m.role, "text": m.text} for m in msgs]


@router.get("/{pack_id}/requirements")
async def list_requirements(pack_id: str, tenant: str = Depends(authed_tenant),
                            reqs=Depends(get_requirements)) -> list[PackRequirement]:
    return await reqs.list(tenant, pack_id)


@router.get("/{pack_id}/status")
async def generation_status(pack_id: str, tenant: str = Depends(authed_tenant),
                            packs=Depends(get_rfp_packs)) -> dict:
    """Per-artifact progress of the background tender-generation job (the frontend polls this).
    Empty until an upload starts a job. See app.modules.rfp.generation for the gen_status shape."""
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    return pack.gen_status or {}


@router.get("/{pack_id}/assignees")
async def list_assignees(pack_id: str, tenant: str = Depends(authed_tenant),
                         packs=Depends(get_rfp_packs), users=Depends(get_user_store)) -> list[dict]:
    """The tenant's users, for the stepper's per-section Reviewer assign dropdown. Tenant-scoped:
    only members of the caller's own tenant are returned. Name falls back to the email local part
    since users carry no separate display name yet."""
    await _require_pack(pack_id, tenant, packs)
    people = await users.list_by_tenant(tenant)
    return [{"id": u.id, "name": (u.email.split("@")[0] if u.email else u.id), "email": u.email}
            for u in people]


@router.post("/{pack_id}/confirm-assignments")
async def confirm_assignments(pack_id: str, request: Request,
                              tenant: str = Depends(authed_tenant),
                              _role: dict = Depends(require_role(Role.editor)),
                              packs=Depends(get_rfp_packs)) -> dict:
    """The stepper's "Confirm Assignments" button (Assigned->Drafting). Sets a top-level
    assignments_confirmed=true into the pack's gen_status (merged, so per-artifact progress is
    preserved) -- purely a stepper-progression marker, nothing server-side is gated on it (drafts
    already run for every section regardless of assignment). GET /status returns gen_status."""
    pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    status = dict(pack.gen_status or {})
    status["assignments_confirmed"] = True
    await recheck()
    await packs.set_gen_status(tenant, pack_id, status)
    return status


@router.get("/{pack_id}/brief")
async def get_brief(pack_id: str, tenant: str = Depends(authed_tenant),
                    packs=Depends(get_rfp_packs)) -> dict | None:
    """The persisted Tender Brief from the background job (null until the brief stage is ready)."""
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    return pack.brief


@router.get("/{pack_id}/compliance")
async def get_compliance(pack_id: str, tenant: str = Depends(authed_tenant),
                         packs=Depends(get_rfp_packs)) -> list[dict]:
    """The persisted Compliance checklist from the background job (empty until it is ready)."""
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    return pack.compliance or []


async def _read_tender_text(pack_id: str, tenant: str, file: UploadFile, packs) -> str:
    try:
        await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    data = await file.read()
    try:
        return extract_text(file.filename or "document.txt", data)
    except UnsupportedDocumentError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{pack_id}/compliance")
async def compliance_check(pack_id: str, request: Request, file: UploadFile = File(...),
                           tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)),
                           packs=Depends(get_rfp_packs)) -> list[dict]:
    """On-demand regenerate: extract mandatory pass/fail compliance items from an uploaded tender
    document AND persist them (so the GET .../compliance poll reflects the newest run)."""
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    text = await _read_tender_text(pack_id, tenant, file, packs)
    try:
        await recheck()
        items = await asyncio.to_thread(extract_compliance, text, document_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
        await recheck()
    except ComplianceError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await recheck()
    await packs.set_compliance(tenant, pack_id, items)
    await recheck()
    return items


@router.post("/{pack_id}/brief")
async def tender_brief(pack_id: str, request: Request, file: UploadFile = File(...),
                       tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)),
                       packs=Depends(get_rfp_packs)) -> dict:
    """On-demand regenerate: extract the Bid Context brief (summary/scope/format/dates/success-
    criteria/gaps) from an uploaded tender document AND persist it (so the GET .../brief poll
    reflects the newest run)."""
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    text = await _read_tender_text(pack_id, tenant, file, packs)
    try:
        await recheck()
        brief = await asyncio.to_thread(extract_brief, text, document_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
        await recheck()
    except BriefError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await recheck()
    await packs.set_brief(tenant, pack_id, brief)
    await recheck()
    return brief


@router.post("/{pack_id}/score")
async def score(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs)) -> dict:
    """Qualify this opportunity against the pack's worker's own criteria (Agent.config's
    "opportunity_criteria" -- set via the generic PUT /agents/{id}/config, same as any other
    worker setting, so this is reusable across workers/clients rather than one hardcoded rubric).

    Scores the tender document already on file for this pack (from /extract or /extract-url) --
    this is meant to run *before* committing to a full draft-every-section pass, so it doesn't
    require a fresh upload."""
    pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    if not pack.document_text:
        raise HTTPException(status_code=422, detail="no tender document on file for this pack -- run /extract or /extract-url first")

    await recheck()
    agent = await request.app.state.agents.get(tenant, pack.agent_id)
    await recheck()
    criteria = list(agent.config.get("opportunity_criteria") or [])
    try:
        result = await asyncio.to_thread(score_opportunity, pack.document_text, criteria,
                                         document_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
        await recheck()
        return result
    except ScoringError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


_STATUS_LABELS = {"auto_accept": "AI-drafted (met internal bar)", "human_review": "AI-drafted, for human review"}


_ANSWER_CONCURRENCY = 4  # bounded so a 15-section tender doesn't fire 15 simultaneous LLM calls


def _tree_answer_row(r: PackRequirement, q) -> dict:
    """The single reviewed answer for one requirement, read from its cockpit tree question (never
    a fresh LLM call). Per-question precedence mirrors what the reviewer sees and locks:
    locked user_draft > user_draft (saved) > ai_answer (the drafted answer shown in the cockpit).

    Non-KB (MANUAL/COMPLIANCE) requirements are never AI-drafted -- they carry the team-completion
    note. A KB requirement whose question has no draft yet is returned blank ("not generated")
    rather than being drafted inline on this read/export path."""
    if r.classification != "KB":
        return {"req": r, "answer": "", "confidence": 0.0, "decision": "human_review",
                "citations": [], "note": f"{r.classification}: to be completed by the team, not drafted by AI."}
    if q is None:
        return {"req": r, "answer": "", "confidence": 0.0, "decision": "human_review",
                "citations": [], "note": ""}
    if q.locked and q.user_draft:
        answer, note = q.user_draft, "Human-approved (locked); reviewer draft overrides the AI answer."
    elif q.user_draft:
        answer, note = q.user_draft, ""
    else:
        answer, note = q.ai_answer or "", ""
    return {"req": r, "answer": answer, "confidence": round(q.grounding, 2),
            "decision": q.decision or "human_review", "citations": list(q.ai_sources), "note": note}


async def _regenerate_tree(request: Request, tenant: str, pack_id: str, tree,
                           packs) -> None:
    """Explicit editor-triggered regenerate (force=true): re-draft every non-locked question in a
    non-manual section via the SAME grounded generator the cockpit uses, persisting each result
    onto its tree question. Fails closed with 503 on a StubProvider fallback (mirroring
    generation.generate_question) so echo text is never persisted or exported. Locked questions
    (human sign-off) and manual sections are left untouched."""
    pack, worker, recheck = await _resolve_pack_worker(
        request, tenant, pack_id, packs)
    await recheck()
    manual_sections = {s.id for s in await tree.sections.list(tenant, pack_id) if s.manual}
    to_draft = [q for q in await tree.questions.list(tenant, pack_id)
                if q.section_id not in manual_sections and not q.locked]
    semaphore = asyncio.Semaphore(_ANSWER_CONCURRENCY)

    async def _regen(q):
        async with semaphore:
            return await generate_question_core(
                tenant, q, worker, tree, recheck_worker=recheck,
                reference_doc_id=pack.reference_doc_id)

    try:
        await asyncio.gather(*(_regen(q) for q in to_draft))
    except StubProviderUnavailable as e:
        raise HTTPException(status_code=503, detail="answer generation is temporarily unavailable") from e


async def _answer_pack(request: Request, tenant: str, pack_id: str, reqs, answers, *,
                       force: bool = False, tree=None, packs=None) -> list[dict]:
    """Build the pack's deliverable answer set from the REVIEWED section/question tree -- exactly
    what the reviewer approved in the cockpit -- so /answers and every export reflect the tree and
    never silently re-draft or emit StubProvider echo text.

    Per requirement the answer comes from its tree question, precedence locked user_draft >
    user_draft > ai_answer (see _tree_answer_row). This is a pure READ: it does NOT trigger any
    LLM drafting. `force=True` is the explicit editor-triggered regenerate path only: it re-runs
    the grounded generator over the tree first (failing closed with 503 on a stub), then reads the
    freshly persisted tree answers back."""
    requirements = await reqs.list(tenant, pack_id)
    if not requirements:
        raise HTTPException(status_code=404, detail="no extracted requirements for this pack -- run /extract first")
    if force:
        await _regenerate_tree(request, tenant, pack_id, tree, packs)
    by_req = {q.req_id: q for q in await tree.questions.list(tenant, pack_id) if q.req_id}
    return [_tree_answer_row(r, by_req.get(r.req_id)) for r in requirements]


class FeedbackBody(BaseModel):
    req_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)  # Approve | Edit | Reject
    comment: str = ""


@router.post("/{pack_id}/feedback")
async def submit_feedback(pack_id: str, body: FeedbackBody, request: Request,
                          claims: dict = Depends(current_claims),
                          tenant: str = Depends(authed_tenant),
                          _role: dict = Depends(require_role(Role.editor)),
                          packs=Depends(get_rfp_packs)) -> dict:
    """Human sign-off on an AI draft. Approve/Edit writes the (possibly edited) text back to the
    knowledge base as trusted ground truth for this requirement type -- the feedback flywheel
    (see AgentCore.record_feedback) -- so the next tender's draft for a similar requirement type
    starts from what a human already approved. Reject records the decision without touching the KB."""
    pack, worker, recheck = await _resolve_pack_worker(request, tenant, pack_id, packs)
    if body.decision not in {"Approve", "Edit", "Reject"}:
        raise HTTPException(status_code=422, detail="decision must be Approve, Edit, or Reject")
    planted = bool(body.decision in {"Approve", "Edit"} and body.comment.strip())
    if planted:
        await worker.approve(
            body.req_id, body.comment.strip(), agent_id=pack.agent_id,
            recheck_worker=recheck)
    await recheck()
    # Every decision is recorded, including Reject, which touches no knowledge base. A review where
    # somebody said no is as much a decision as one where they said yes, and an audit that only holds
    # the approvals cannot show that a draft was looked at and turned down.
    #
    # `planted` distinguishes the two that matter operationally: an Approve with an empty comment writes
    # nothing to the knowledge base, so it did not create ground truth however it was labelled in the UI.
    await _record_governance(
        request, audit_actions.ANSWER_APPROVED, tenant, claims,
        target_id=body.req_id, pack_id=pack_id,
        before={}, after={"decision": body.decision.lower(),
                          # Not the text: it is customer content, already durable in the knowledge base,
                          # and copying it here would duplicate it into a store with a different
                          # retention and a different erasure path.
                          "characters": len(body.comment.strip())},
        metadata={"agent_id": pack.agent_id, "source": "tender_review",
                  "wrote_ground_truth": planted})
    return {"req_id": body.req_id, "decision": body.decision, "saved": True}


@router.get("/{pack_id}/answers")
async def get_answers(pack_id: str, request: Request, force: bool = False,
                      tenant: str = Depends(authed_tenant), claims: dict = Depends(current_claims),
                      packs=Depends(get_rfp_packs), reqs=Depends(get_requirements),
                      answers=Depends(get_pack_answers), tree=Depends(get_pack_tree)) -> list[dict]:
    """JSON form of the same answer-pack pipeline the exports use -- powers the tender cockpit's
    Sections tab (AI draft + confidence/grounding + citations + status per requirement).
    force=true bypasses the cache and re-drafts every KB requirement (Regenerate all) -- a real
    LLM call per requirement, so (unlike the plain cached read) it needs Editor-or-above, not just
    any authenticated viewer, to avoid unbounded regeneration cost from a read-only role."""
    if force and not role_allows(claims.get("role", "viewer"), Role.editor):
        raise HTTPException(status_code=403, detail="insufficient role to regenerate answers")
    answered = await _answer_pack(
        request, tenant, pack_id, reqs, answers, force=force, tree=tree, packs=packs)
    return [{
        "req_id": a["req"].req_id, "req_title": a["req"].title, "classification": a["req"].classification,
        "requirement": a["req"].requirement, "answer": a["answer"], "confidence": a["confidence"],
        "grounding": a["confidence"], "status": a["decision"], "citations": a["citations"], "note": a["note"],
    } for a in answered]


@router.get("/{pack_id}/export/xlsx")
async def export_xlsx(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                      reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                      tree=Depends(get_pack_tree)) -> StreamingResponse:
    """Coverage sheet: one row per requirement, with a Grounding % column and human-readable
    status, plus blank Review/Comment columns for offline reviewer sign-off."""
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers, tree=tree)
    rows = [["ID", "Requirement", "AI Answer", "Confidence", "Grounding %", "Status", "KB Sources",
             "Review (Approve/Edit/Reject)", "Comment / Edited answer"]]
    for a in answered:
        r = a["req"]
        status = a["note"] or _STATUS_LABELS.get(a["decision"], a["decision"])
        rows.append([r.req_id, r.title, a["answer"], a["confidence"], round(a["confidence"] * 100, 1),
                    status, "; ".join(a["citations"]), "", ""])
    xlsx_bytes = build_xlsx("Coverage", rows)
    return StreamingResponse(io.BytesIO(xlsx_bytes),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=rfp-coverage.xlsx"})


@router.get("/{pack_id}/export/docx-clean")
async def export_docx_clean(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                            reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                            tree=Depends(get_pack_tree)) -> StreamingResponse:
    """Client-ready submission: per-section heading + answer prose only, no confidence/citation
    annotations. Un-drafted (non-KB) sections show a placeholder for the team to complete."""
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers, tree=tree)
    paragraphs = []
    for a in answered:
        r = a["req"]
        paragraphs.append(f"{r.req_id}. {r.title}")
        paragraphs.append(a["answer"] or f"[To be completed by the team in the prescribed format: {r.classification}]")
    docx_bytes = build_docx("Tender Response", paragraphs)
    return StreamingResponse(io.BytesIO(docx_bytes),
                             media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             headers={"Content-Disposition": "attachment; filename=submission.docx"})


@router.get("/{pack_id}/export/docx-review")
async def export_docx_review(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                             reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                             tree=Depends(get_pack_tree)) -> StreamingResponse:
    """Internal annotated variant: requirement text + confidence/status note + answer + KB
    sources -- for human review before the clean submission is finalised."""
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers, tree=tree)
    paragraphs = []
    for a in answered:
        r = a["req"]
        paragraphs.append(f"{r.req_id}. {r.title}")
        paragraphs.append(f"Requirement: {r.requirement}")
        status = a["note"] or f"[AI-drafted - confidence {round(a['confidence'] * 100)}% - {a['decision']}]"
        paragraphs.append(status)
        paragraphs.append(a["answer"] or "(not drafted)")
        if a["citations"]:
            paragraphs.append(f"Knowledge base sources: {'; '.join(a['citations'])}")
    docx_bytes = build_docx("Tender Response - Review Draft", paragraphs)
    return StreamingResponse(io.BytesIO(docx_bytes),
                             media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             headers={"Content-Disposition": "attachment; filename=review-draft.docx"})


# --- Section -> question tree (the validated tender cockpit model, app.modules.rfp.tree) ---------
# Sections own questions; each question carries a grounded AI draft plus an editable/lockable human
# draft. Locking rolls up (section locked <=> all its questions locked; pack -> final needs all
# sections locked). Reads are open to any authenticated tenant viewer; mutations need Editor+.

async def _require_pack(pack_id: str, tenant: str, packs) -> None:
    try:
        await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e


class SectionBody(BaseModel):
    code: str = ""
    name: str = Field(min_length=1)
    page: int | None = None
    weighting: str = ""
    parent_id: str | None = None
    assigned_reviewer_user_id: str | None = None
    assigned_reviewer_name: str = ""
    due_date: str | None = None
    manual: bool = False


class SectionPatch(BaseModel):
    code: str | None = None
    name: str | None = None
    page: int | None = None
    weighting: str | None = None
    status: str | None = None
    parent_id: str | None = None
    assigned_reviewer_user_id: str | None = None
    assigned_reviewer_name: str | None = None
    due_date: str | None = None
    manual: bool | None = None


class QuestionBody(BaseModel):
    text: str = Field(min_length=1)
    word_limit: int | None = None


class QuestionPatch(BaseModel):
    text: str | None = None
    word_limit: int | None = None


class DraftBody(BaseModel):
    user_draft: str = ""


@router.get("/{pack_id}/sections")
async def list_sections(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                        packs=Depends(get_rfp_packs), reqs=Depends(get_requirements),
                        tree=Depends(get_pack_tree)) -> list[dict]:
    """The full section->question tree for a pack (each section with its nested questions).

    Packs extracted before the tree feature (migration 0018) have flat requirements but an empty
    tree; backfill it lazily from those stored requirements on first view so old packs "just work"
    -- idempotent (never rebuilds an existing tree), tenant-scoped, and no LLM re-run."""
    await _require_pack(pack_id, tenant, packs)
    rows = await tree.list_tree(tenant, pack_id)
    if not rows:
        requirements = await reqs.list(tenant, pack_id)
        if requirements:
            _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
            await recheck()
            await tree.populate_from_requirements(
                tenant, pack_id, requirements, recheck_worker=recheck)
            await recheck()
            rows = await tree.list_tree(tenant, pack_id)
    return rows


@router.post("/{pack_id}/sections")
async def add_section(pack_id: str, body: SectionBody, request: Request,
                      tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs),
                      tree=Depends(get_pack_tree)) -> PackSection:
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    if body.parent_id:
        try:
            await tree.get_section_for_pack(tenant, pack_id, body.parent_id)
        except PackSectionNotFound as e:
            raise HTTPException(status_code=404, detail="section not found") from e
    await recheck()
    return await tree.add_section(tenant, pack_id, code=body.code, name=body.name, page=body.page,
                                  weighting=body.weighting, parent_id=body.parent_id,
                                  assigned_reviewer_user_id=body.assigned_reviewer_user_id,
                                  assigned_reviewer_name=body.assigned_reviewer_name,
                                  due_date=body.due_date, manual=body.manual)


@router.patch("/{pack_id}/sections/{section_id}")
async def edit_section(pack_id: str, section_id: str, body: SectionPatch, request: Request,
                       tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)),
                       packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> PackSection:
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_section_for_pack(tenant, pack_id, section_id)
        patch = body.model_dump(exclude_unset=True)
        parent_id = patch.get("parent_id")
        if parent_id == section_id:
            raise HTTPException(status_code=422, detail="section cannot be its own parent")
        if parent_id:
            await tree.get_section_for_pack(tenant, pack_id, parent_id)
        await recheck()
        return await tree.update_section(tenant, section_id, **patch)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e


class ReviewerBody(BaseModel):
    reviewer: str | None = None  # a tenant user id; null clears the assignment
    reviewer_name: str = ""  # denormalised display name so the Reviewer column renders without a join


@router.put("/{pack_id}/sections/{section_id}/reviewer")
async def set_section_reviewer(pack_id: str, section_id: str, body: ReviewerBody,
                               request: Request, tenant: str = Depends(authed_tenant),
                               _role: dict = Depends(require_role(Role.editor)),
                               packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> PackSection:
    """Assign (or clear, with reviewer=null) the per-section stepper reviewer. Metadata only --
    it does NOT change whether/what answers are generated (drafts run for every section)."""
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_section_for_pack(tenant, pack_id, section_id)
        await recheck()
        return await tree.set_reviewer(tenant, section_id, reviewer=body.reviewer,
                                       reviewer_name=body.reviewer_name)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e


@router.delete("/{pack_id}/sections/{section_id}")
async def delete_section(pack_id: str, section_id: str, request: Request,
                         tenant: str = Depends(authed_tenant),
                         _role: dict = Depends(require_role(Role.editor)),
                         packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> dict:
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_section_for_pack(tenant, pack_id, section_id)
        await recheck()
        await tree.delete_section(tenant, section_id)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e
    return {"deleted": section_id}


@router.post("/{pack_id}/sections/{section_id}/questions")
async def add_question(pack_id: str, section_id: str, body: QuestionBody, request: Request,
                       tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)),
                       packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)):
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_section_for_pack(tenant, pack_id, section_id)
        await recheck()
        return await tree.add_question(tenant, section_id, text=body.text, word_limit=body.word_limit)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e


@router.patch("/{pack_id}/questions/{question_id}")
async def edit_question(pack_id: str, question_id: str, body: QuestionPatch, request: Request,
                        tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)):
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_question_for_pack(tenant, pack_id, question_id)
        await recheck()
        return await tree.update_question(tenant, question_id, **body.model_dump(exclude_unset=True))
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


@router.delete("/{pack_id}/questions/{question_id}")
async def delete_question(pack_id: str, question_id: str, request: Request,
                          tenant: str = Depends(authed_tenant),
                          _role: dict = Depends(require_role(Role.editor)),
                          packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> dict:
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_question_for_pack(tenant, pack_id, question_id)
        await recheck()
        await tree.delete_question(tenant, question_id)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e
    return {"deleted": question_id}


@router.put("/{pack_id}/questions/{question_id}/draft")
async def save_draft(pack_id: str, question_id: str, body: DraftBody, request: Request,
                     tenant: str = Depends(authed_tenant),
                     _role: dict = Depends(require_role(Role.editor)),
                     packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)):
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_question_for_pack(tenant, pack_id, question_id)
        await recheck()
        return await tree.save_user_draft(tenant, question_id, body.user_draft)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


async def _record_governance(request, action: str, tenant: str, claims: dict, *,
                             target_id: str, pack_id: str, before: dict, after: dict,
                             metadata: dict | None = None) -> None:
    """Record a tender governance event.

    One shape for all five, because they are the same kind of fact: a named person made a decision about
    what this bid says. Nothing recorded any of them, so a pack could be locked, reopened, finalised and
    marked won with no trace of who decided any of it. For a document a customer submits to a public
    body, that is the gap that matters most in this module.
    """
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=action, target_id=target_id, target_label=pack_id, tenant_id=tenant,
        actor_type=audit.USER, actor_id=str(claims.get("sub") or ""),
        actor_label=str(claims.get("email") or ""),
        changes=audit.diff(action, before, after),
        metadata={"pack_id": pack_id, **(metadata or {})}), request=request)


@router.post("/{pack_id}/questions/{question_id}/lock")
async def lock_question(pack_id: str, question_id: str, request: Request,
                        claims: dict = Depends(current_claims),
                        tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)):
    """Lock an answer: a person saying "this is what we are submitting"."""
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        existing = await tree.get_question_for_pack(tenant, pack_id, question_id)
        # The BOOLEAN, not the object. The in-memory store returns live rows, so reading
        # existing.locked after the mutation reads the value the mutation just wrote, and every lock
        # would have looked like a re-lock. This is the same shape of mistake the credential audit hit,
        # and it fails the same way: silently, with the row simply absent.
        was_locked = bool(getattr(existing, "locked", False))
        await recheck()
        locked = await tree.lock_question(tenant, question_id, locked=True)
        # Only when it actually changed: re-locking an already locked answer is not a second sign-off,
        # and a stream of them would bury the real ones.
        if not was_locked:
            await _record_governance(
                request, audit_actions.ANSWER_LOCKED, tenant, claims,
                target_id=question_id, pack_id=pack_id,
                before={"locked": False}, after={"locked": True})
        return locked
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


@router.post("/{pack_id}/questions/{question_id}/unlock")
async def unlock_question(pack_id: str, question_id: str, request: Request,
                          claims: dict = Depends(current_claims),
                          tenant: str = Depends(authed_tenant),
                          _role: dict = Depends(require_role(Role.editor)),
                          packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)):
    """Reopen a locked answer, which reverses a sign-off.

    Recorded as its own action rather than a lock with locked=false, because reversing an approval after
    review is the move a bid team would be asked about afterwards, and it should be findable without
    reading the diff of every lock event.
    """
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        existing = await tree.get_question_for_pack(tenant, pack_id, question_id)
        # See lock_question: the boolean has to be captured before the mutation.
        was_locked = bool(getattr(existing, "locked", False))
        await recheck()
        unlocked = await tree.lock_question(tenant, question_id, locked=False)
        if was_locked:
            await _record_governance(
                request, audit_actions.ANSWER_UNLOCKED, tenant, claims,
                target_id=question_id, pack_id=pack_id,
                before={"locked": True}, after={"locked": False})
        return unlocked
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


@router.post("/{pack_id}/sections/{section_id}/lock-all")
async def lock_all_in_section(pack_id: str, section_id: str, request: Request,
                              claims: dict = Depends(current_claims),
                              tenant: str = Depends(authed_tenant),
                              _role: dict = Depends(require_role(Role.editor)),
                              packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> PackSection:
    """Bulk sign-off: one click locking every answer in a section."""
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_section_for_pack(tenant, pack_id, section_id)
        await recheck()
        # Counted before, because afterwards every one is locked and the number would always equal the
        # section size. How many answers this click signed off is the substance of a bulk approval.
        unlocked_before = len([q for q in await tree.questions.list_for_section(tenant, section_id)
                               if not getattr(q, "locked", False)])
        section = await tree.lock_all_in_section(tenant, section_id)
        if unlocked_before:
            await _record_governance(
                request, audit_actions.SECTION_LOCKED, tenant, claims,
                target_id=section_id, pack_id=pack_id,
                before={}, after={"questions_locked": unlocked_before})
        return section
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e


async def _generate_question(tenant: str, question, worker, tree, recheck: WorkerRecheck,
                             reference_doc_id: str | None = None):
    """Draft one question with agentcore (shared with the background job's drafts stage -- see
    app.modules.rfp.generation.generate_question). A StubProvider fallback (e.g. Bedrock outage)
    echoes context rather than a real grounded answer, so it is never persisted; fail closed with
    503 so the reviewer sees an outage, not a fabricated-looking draft they might lock and submit."""
    try:
        return await generate_question_core(
            tenant, question, worker, tree, recheck_worker=recheck,
            reference_doc_id=reference_doc_id)
    except StubProviderUnavailable as e:
        raise HTTPException(status_code=503, detail="answer generation is temporarily unavailable") from e


@router.post("/{pack_id}/questions/{question_id}/generate")
async def generate_question(pack_id: str, question_id: str, request: Request,
                            tenant: str = Depends(authed_tenant),
                            _role: dict = Depends(require_role(Role.editor)),
                            packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)):
    pack, worker, recheck = await _resolve_pack_worker(request, tenant, pack_id, packs)
    try:
        question = await tree.get_question_for_pack(tenant, pack_id, question_id)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e
    return await _generate_question(tenant, question, worker, tree, recheck,
                                    pack.reference_doc_id)


@router.post("/{pack_id}/sections/{section_id}/generate")
async def generate_section(pack_id: str, section_id: str, request: Request,
                           tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)),
                           packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> list:
    pack, worker, recheck = await _resolve_pack_worker(request, tenant, pack_id, packs)
    try:
        section = await tree.get_section_for_pack(tenant, pack_id, section_id)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e
    if section.manual:
        await recheck()
        return []
    out = []
    for q in await tree.questions.list_for_section(tenant, section_id):
        await tree.get_question_for_pack(tenant, pack_id, q.id)
        out.append(await _generate_question(tenant, q, worker, tree, recheck,
                                            pack.reference_doc_id))
    return out


@router.post("/{pack_id}/generate")
async def generate_pack(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> list:
    """Whole-pack draft: every non-locked question in every non-manual section, via agentcore."""
    pack, worker, recheck = await _resolve_pack_worker(request, tenant, pack_id, packs)
    manual_sections = {s.id for s in await tree.sections.list(tenant, pack_id) if s.manual}
    out = []
    for q in await tree.questions.list(tenant, pack_id):
        if q.section_id in manual_sections:
            continue
        await tree.get_question_for_pack(tenant, pack_id, q.id)
        out.append(await _generate_question(tenant, q, worker, tree, recheck,
                                            pack.reference_doc_id))
    return out


@router.get("/{pack_id}/overview")
async def pack_overview(pack_id: str, tenant: str = Depends(authed_tenant),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> dict:
    """Cockpit header metrics: sections, AI-drafted X/Y, for-human-review, KB-sources counts."""
    await _require_pack(pack_id, tenant, packs)
    return await tree.overview(tenant, pack_id)
