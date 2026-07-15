"""RFP pack HTTP API (tenant-scoped): create/list/get/delete tenders a worker is answering."""
from __future__ import annotations

import asyncio
import io

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.deps import (
    authed_tenant,
    build_tenant_worker,
    current_claims,
    get_pack_answers,
    get_pack_tree,
    get_requirements,
    get_rfp_packs,
    get_teams_notifier,
    require_role,
)
from app.modules.ai.gateway import get_provider
from app.modules.chat.files import build_docx, build_xlsx
from app.modules.identity.rbac import Role, role_allows
from app.modules.knowledge.parsing import UnsupportedDocumentError, extract_text
from app.modules.rfp.brief import BriefError, extract_brief
from app.modules.rfp.compliance import ComplianceError, extract_compliance
from app.modules.rfp.extraction import ExtractionError, chunk_document, extract_requirements
from app.modules.rfp.scoring import ScoringError, score_opportunity
from app.modules.rfp.service import CachedAnswer, PackRequirement, RfpPack, RfpPackNotFound
from app.modules.rfp.tree import PackQuestionNotFound, PackSection, PackSectionNotFound

router = APIRouter(prefix="/rfp/packs", tags=["rfp"])

# extract/ask/compliance/brief are one-shot calls over a whole tender document (tens of thousands
# of chars in, a full structured response out) -- the gateway's default read_timeout (20s) is
# tuned for the fast per-requirement answering hot path and is routinely too tight for these.
_DOCUMENT_READ_TIMEOUT = 90


class CreatePackBody(BaseModel):
    agent_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    client_name: str = ""
    deadline: str | None = None


@router.post("")
async def create_pack(body: CreatePackBody, tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs)) -> RfpPack:
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
async def set_stage(pack_id: str, body: StageBody, tenant: str = Depends(authed_tenant),
                    _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs),
                    tree=Depends(get_pack_tree)) -> RfpPack:
    # A pack can only be finalised once every section is locked (lock roll-up governance) -- guard
    # here so the generic stage transition can't skip review sign-off.
    if body.stage == "final" and not await tree.all_sections_locked(tenant, pack_id):
        raise HTTPException(status_code=409, detail="cannot finalise: every section must be locked first")
    try:
        return await svc.set_stage(tenant, pack_id, body.stage)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


class OutcomeBody(BaseModel):
    outcome: str | None = None  # "won" | "lost" | "withdrawn" | null to clear
    reason: str = ""  # loss reason, one of rfp.service.LOSS_REASONS -- only meaningful when lost
    value: float | None = None  # contract value, for "won" pipeline-value reporting


@router.put("/{pack_id}/outcome")
async def set_outcome(pack_id: str, body: OutcomeBody, tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs),
                      notifier=Depends(get_teams_notifier)) -> RfpPack:
    """Win/Loss Analysis: record what happened to a submitted tender. Feeds /rfp/packs/stats."""
    try:
        pack = await svc.set_outcome(tenant, pack_id, outcome=body.outcome, reason=body.reason, value=body.value)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if body.outcome == "won":
        await notifier.notify(tenant, f"\U0001f389 Tender won: **{pack.title}**"
                              + (f" (${body.value:,.0f})" if body.value else ""))
    elif body.outcome == "lost":
        await notifier.notify(tenant, f"Tender lost: **{pack.title}**"
                              + (f" -- reason: {body.reason}" if body.reason else ""))
    return pack


@router.delete("/{pack_id}")
async def delete_pack(pack_id: str, tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs),
                      reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                      tree=Depends(get_pack_tree)) -> dict:
    await answers.delete_for_pack(tenant, pack_id)
    await reqs.delete_for_pack(tenant, pack_id)
    await tree.delete_for_pack(tenant, pack_id)
    await svc.delete(tenant, pack_id)
    return {"deleted": pack_id}


_EXTRACT_CONCURRENCY = 4  # bounded so a huge tender doesn't fire a dozen simultaneous LLM calls


async def _extract_requirements_chunked(text: str) -> list[dict]:
    """Split a large tender document into independent chunks and extract each in parallel,
    instead of one call over the whole document -- see extraction.chunk_document for why: a
    single call over tens of thousands of chars (both the prompt and the expected completion,
    every requirement sub-split where applicable) was routinely hitting Bedrock's read timeout,
    even a generous one. Smaller, parallel chunks are both faster per call and no longer subject
    to extract_requirements' fixed max_chars truncation regardless of the document's real length.

    Chunk results are merged and deduped by id -- the overlap between consecutive chunks means a
    section straddling a boundary can appear in two chunks; the first occurrence wins."""
    chunks = chunk_document(text)
    if len(chunks) == 1:
        return await asyncio.to_thread(extract_requirements, chunks[0], get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))

    semaphore = asyncio.Semaphore(_EXTRACT_CONCURRENCY)

    async def extract_chunk(i: int, chunk: str) -> list[dict]:
        async with semaphore:
            try:
                return await asyncio.to_thread(extract_requirements, chunk,
                                               get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT),
                                               id_prefix=f"c{i}-")
            except ExtractionError:
                return []  # one bad/timed-out chunk shouldn't sink requirements found in the rest

    results = await asyncio.gather(*(extract_chunk(i, c) for i, c in enumerate(chunks)))
    merged: list[dict] = []
    seen_ids: set[str] = set()
    for chunk_items in results:
        for item in chunk_items:
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            merged.append(item)
    if not merged:
        raise ExtractionError("no requirements could be extracted from this document")
    return merged


async def _extract_and_save(tenant: str, pack_id: str, text: str, packs, reqs, answers,
                            tree) -> list[PackRequirement]:
    try:
        extracted = await _extract_requirements_chunked(text)
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Persisted so /ask can ground follow-up questions in the source document later, without
    # re-uploading it.
    await packs.set_document_text(tenant, pack_id, text)
    # A new extraction can rewrite req_ids/content entirely -- drop any cached answers from a
    # previous extraction so the cockpit doesn't show drafts for stale requirements.
    await answers.delete_for_pack(tenant, pack_id)
    # Also (re)build the reviewer-facing section->question tree from the same extraction, grouping
    # items by top-level code into sections (see PackTreeService.populate_from_extraction).
    await tree.populate_from_extraction(tenant, pack_id, extracted)
    return await reqs.save_extracted(tenant, pack_id, extracted)


@router.post("/{pack_id}/extract")
async def extract(pack_id: str, file: UploadFile = File(...), tenant: str = Depends(authed_tenant),
                  _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs),
                  reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                  tree=Depends(get_pack_tree)) -> list[PackRequirement]:
    """Upload any RFP/tender document and extract its requirements -- no per-tender code needed."""
    try:
        await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e

    data = await file.read()
    try:
        text = extract_text(file.filename or "document.txt", data)
    except UnsupportedDocumentError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return await _extract_and_save(tenant, pack_id, text, packs, reqs, answers, tree)


class ExtractUrlBody(BaseModel):
    url: str = Field(min_length=1, pattern=r"^https?://")


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


@router.post("/{pack_id}/extract-url")
async def extract_from_url(pack_id: str, body: ExtractUrlBody, tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs),
                           reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                           tree=Depends(get_pack_tree)) -> list[PackRequirement]:
    """Same as /extract, but sourced from a tender published on a webpage instead of an uploaded
    file -- fetches the URL, extracts its text (HTML or a direct PDF/DOCX link both work, since
    extract_text dispatches on the response's actual content type), and runs the same chunked
    extraction pipeline. No separate scraping infrastructure: one tender page is one request."""
    try:
        await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e

    import httpx

    _assert_public_url(body.url)
    try:
        # Redirects deliberately NOT followed -- a redirect target skips the public-address
        # check above, which would defeat it.
        resp = await asyncio.to_thread(httpx.get, body.url, timeout=20.0, follow_redirects=False,
                                       headers={"User-Agent": "Mozilla/5.0 (compatible; QikoBot/1.0)"})
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

    return await _extract_and_save(tenant, pack_id, text, packs, reqs, answers, tree)


class AskBody(BaseModel):
    question: str = Field(min_length=1)


@router.post("/{pack_id}/ask")
async def ask_bid_context(pack_id: str, body: AskBody, tenant: str = Depends(authed_tenant),
                          packs=Depends(get_rfp_packs)) -> dict:
    """Bid Context Q&A: answer ad-hoc questions about the tender itself (scope, rules, format,
    deadlines, risks) grounded ONLY in the uploaded tender document -- distinct from the
    requirement-answering flow, which draws on the tenant's knowledge base instead. Port of
    idg-worker's app/agents/bid_context.py."""
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    if not pack.document_text:
        raise HTTPException(status_code=422, detail="no tender document on file for this pack -- run /extract first")

    system = ("You are a tender analyst. Answer questions about THIS tender using ONLY the tender "
             "document provided. Be precise about scope, submission format, deadlines, "
             "qualification rules and risks. If the document doesn't state it, say so -- do not guess.")
    prompt = f"TENDER DOCUMENT:\n{pack.document_text[:60_000]}\n\nQUESTION: {body.question}\n\nAnswer from the document only."
    response = await asyncio.to_thread(get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT).generate,
                                       prompt, system=system, temperature=0.0)
    return {"question": body.question, "answer": response.text}


@router.get("/{pack_id}/requirements")
async def list_requirements(pack_id: str, tenant: str = Depends(authed_tenant),
                            reqs=Depends(get_requirements)) -> list[PackRequirement]:
    return await reqs.list(tenant, pack_id)


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
async def compliance_check(pack_id: str, file: UploadFile = File(...), tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)),
                           packs=Depends(get_rfp_packs)) -> list[dict]:
    """Extract mandatory pass/fail compliance items from an uploaded tender document."""
    text = await _read_tender_text(pack_id, tenant, file, packs)
    try:
        return await asyncio.to_thread(extract_compliance, text, get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
    except ComplianceError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{pack_id}/brief")
async def tender_brief(pack_id: str, file: UploadFile = File(...), tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)),
                       packs=Depends(get_rfp_packs)) -> dict:
    """Extract the Bid Context brief (summary/scope/format/dates/success-criteria/gaps) from an
    uploaded tender document."""
    text = await _read_tender_text(pack_id, tenant, file, packs)
    try:
        return await asyncio.to_thread(extract_brief, text, get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
    except BriefError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{pack_id}/score")
async def score(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs)) -> dict:
    """Qualify this opportunity against the pack's worker's own criteria (Agent.config's
    "opportunity_criteria" -- set via the generic PUT /agents/{id}/config, same as any other
    worker setting, so this is reusable across workers/clients rather than one hardcoded rubric).

    Scores the tender document already on file for this pack (from /extract or /extract-url) --
    this is meant to run *before* committing to a full draft-every-section pass, so it doesn't
    require a fresh upload."""
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    if not pack.document_text:
        raise HTTPException(status_code=422, detail="no tender document on file for this pack -- run /extract or /extract-url first")

    agent = await request.app.state.agents.get(tenant, pack.agent_id) if pack.agent_id else None
    criteria = list((agent.config.get("opportunity_criteria") if agent else None) or [])
    try:
        return await asyncio.to_thread(score_opportunity, pack.document_text, criteria,
                                       get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
    except ScoringError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


_STATUS_LABELS = {"auto_accept": "AI-drafted (met internal bar)", "human_review": "AI-drafted, for human review"}


_ANSWER_CONCURRENCY = 4  # bounded so a 15-section tender doesn't fire 15 simultaneous LLM calls


async def _answer_pack(request: Request, tenant: str, pack_id: str, reqs, answers, *,
                       force: bool = False, tree=None) -> list[dict]:
    """Answer every KB requirement in the pack, backed by a Postgres cache (rfp_pack_answers) so a
    15-section tender isn't re-drafted (each section a real LLM call) on every page visit -- only
    the first time, or when force=True (the cockpit's per-section Regenerate action).

    When `tree` is given, a locked question's human user_draft overrides the AI draft for its
    requirement (idg-worker's human-answer overlay governance -- the reviewer's approved text is
    the source of truth in the output)."""
    requirements = await reqs.list(tenant, pack_id)
    if not requirements:
        raise HTTPException(status_code=404, detail="no extracted requirements for this pack -- run /extract first")
    # Answer as the specific worker this tender belongs to, not a generic tenant-wide one -- so a
    # pack owned by e.g. a "Pre Sales Writer" agent drafts in that worker's own voice/threshold.
    pack = await request.app.state.rfp_packs.get(tenant, pack_id)
    worker = await build_tenant_worker(request, tenant, agent_id=pack.agent_id if pack else None)
    semaphore = asyncio.Semaphore(_ANSWER_CONCURRENCY)
    cached = {} if force else await answers.get_all(tenant, pack_id)

    async def answer_one(r: PackRequirement) -> dict:
        if r.classification != "KB":
            return {"req": r, "answer": "", "confidence": 0.0, "decision": "human_review",
                   "citations": [], "note": f"{r.classification}: to be completed by the team, not drafted by AI."}
        hit = cached.get(r.req_id)
        if hit is not None:
            return {"req": r, "answer": hit.answer, "confidence": hit.confidence,
                   "decision": hit.decision, "citations": hit.citations, "note": hit.note}
        async with semaphore:
            result = await worker.answer(r.req_id, r.requirement)
        out = {"req": r, "answer": result.answer, "confidence": round(result.critique.grounding, 2),
              "decision": result.decision.value, "citations": result.citations, "note": ""}
        await answers.put(tenant, pack_id, r.req_id, CachedAnswer(
            pack_id=pack_id, req_id=r.req_id, tenant=tenant, answer=out["answer"],
            confidence=out["confidence"], decision=out["decision"], citations=out["citations"], note=out["note"]))
        return out

    # Runs the (now off-event-loop) LLM calls concurrently, bounded by the semaphore, instead of
    # one requirement at a time -- cuts wall-clock time for a multi-section tender roughly in
    # proportion to the concurrency limit instead of the total requirement count.
    out = list(await asyncio.gather(*(answer_one(r) for r in requirements)))
    if tree is not None:
        overlay = {q.req_id: q.user_draft for q in await tree.questions.list(tenant, pack_id)
                   if q.locked and q.user_draft and q.req_id}
        for a in out:
            override = overlay.get(a["req"].req_id)
            if override:
                a["answer"] = override
                a["note"] = "Human-approved (locked); reviewer draft overrides the AI answer."
    return out


class FeedbackBody(BaseModel):
    req_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)  # Approve | Edit | Reject
    comment: str = ""


@router.post("/{pack_id}/feedback")
async def submit_feedback(pack_id: str, body: FeedbackBody, request: Request,
                          tenant: str = Depends(authed_tenant),
                          _role: dict = Depends(require_role(Role.editor)),
                          packs=Depends(get_rfp_packs)) -> dict:
    """Human sign-off on an AI draft. Approve/Edit writes the (possibly edited) text back to the
    knowledge base as trusted ground truth for this requirement type -- the feedback flywheel
    (see AgentCore.record_feedback) -- so the next tender's draft for a similar requirement type
    starts from what a human already approved. Reject records the decision without touching the KB."""
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    if body.decision not in {"Approve", "Edit", "Reject"}:
        raise HTTPException(status_code=422, detail="decision must be Approve, Edit, or Reject")
    if body.decision in {"Approve", "Edit"} and body.comment.strip():
        worker = await build_tenant_worker(request, tenant, agent_id=pack.agent_id)
        await worker.approve(body.req_id, body.comment.strip())
    return {"req_id": body.req_id, "decision": body.decision, "saved": True}


@router.get("/{pack_id}/answers")
async def get_answers(pack_id: str, request: Request, force: bool = False,
                      tenant: str = Depends(authed_tenant), claims: dict = Depends(current_claims),
                      reqs=Depends(get_requirements), answers=Depends(get_pack_answers),
                      tree=Depends(get_pack_tree)) -> list[dict]:
    """JSON form of the same answer-pack pipeline the exports use -- powers the tender cockpit's
    Sections tab (AI draft + confidence/grounding + citations + status per requirement).
    force=true bypasses the cache and re-drafts every KB requirement (Regenerate all) -- a real
    LLM call per requirement, so (unlike the plain cached read) it needs Editor-or-above, not just
    any authenticated viewer, to avoid unbounded regeneration cost from a read-only role."""
    if force and not role_allows(claims.get("role", "viewer"), Role.editor):
        raise HTTPException(status_code=403, detail="insufficient role to regenerate answers")
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers, force=force, tree=tree)
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
async def list_sections(pack_id: str, tenant: str = Depends(authed_tenant),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> list[dict]:
    """The full section->question tree for a pack (each section with its nested questions)."""
    await _require_pack(pack_id, tenant, packs)
    return await tree.list_tree(tenant, pack_id)


@router.post("/{pack_id}/sections")
async def add_section(pack_id: str, body: SectionBody, tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs),
                      tree=Depends(get_pack_tree)) -> PackSection:
    await _require_pack(pack_id, tenant, packs)
    return await tree.add_section(tenant, pack_id, code=body.code, name=body.name, page=body.page,
                                  weighting=body.weighting, parent_id=body.parent_id,
                                  assigned_reviewer_user_id=body.assigned_reviewer_user_id,
                                  assigned_reviewer_name=body.assigned_reviewer_name,
                                  due_date=body.due_date, manual=body.manual)


@router.patch("/{pack_id}/sections/{section_id}")
async def edit_section(pack_id: str, section_id: str, body: SectionPatch,
                       tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)),
                       tree=Depends(get_pack_tree)) -> PackSection:
    try:
        return await tree.update_section(tenant, section_id, **body.model_dump(exclude_unset=True))
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e


@router.delete("/{pack_id}/sections/{section_id}")
async def delete_section(pack_id: str, section_id: str, tenant: str = Depends(authed_tenant),
                         _role: dict = Depends(require_role(Role.editor)),
                         tree=Depends(get_pack_tree)) -> dict:
    try:
        await tree.delete_section(tenant, section_id)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e
    return {"deleted": section_id}


@router.post("/{pack_id}/sections/{section_id}/questions")
async def add_question(pack_id: str, section_id: str, body: QuestionBody,
                       tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)),
                       tree=Depends(get_pack_tree)):
    try:
        return await tree.add_question(tenant, section_id, text=body.text, word_limit=body.word_limit)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e


@router.patch("/{pack_id}/questions/{question_id}")
async def edit_question(pack_id: str, question_id: str, body: QuestionPatch,
                        tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        tree=Depends(get_pack_tree)):
    try:
        return await tree.update_question(tenant, question_id, **body.model_dump(exclude_unset=True))
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


@router.delete("/{pack_id}/questions/{question_id}")
async def delete_question(pack_id: str, question_id: str, tenant: str = Depends(authed_tenant),
                          _role: dict = Depends(require_role(Role.editor)),
                          tree=Depends(get_pack_tree)) -> dict:
    try:
        await tree.delete_question(tenant, question_id)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e
    return {"deleted": question_id}


@router.put("/{pack_id}/questions/{question_id}/draft")
async def save_draft(pack_id: str, question_id: str, body: DraftBody,
                     tenant: str = Depends(authed_tenant),
                     _role: dict = Depends(require_role(Role.editor)),
                     tree=Depends(get_pack_tree)):
    try:
        return await tree.save_user_draft(tenant, question_id, body.user_draft)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


@router.post("/{pack_id}/questions/{question_id}/lock")
async def lock_question(pack_id: str, question_id: str, tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        tree=Depends(get_pack_tree)):
    try:
        return await tree.lock_question(tenant, question_id, locked=True)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


@router.post("/{pack_id}/questions/{question_id}/unlock")
async def unlock_question(pack_id: str, question_id: str, tenant: str = Depends(authed_tenant),
                          _role: dict = Depends(require_role(Role.editor)),
                          tree=Depends(get_pack_tree)):
    try:
        return await tree.lock_question(tenant, question_id, locked=False)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e


@router.post("/{pack_id}/sections/{section_id}/lock-all")
async def lock_all_in_section(pack_id: str, section_id: str, tenant: str = Depends(authed_tenant),
                              _role: dict = Depends(require_role(Role.editor)),
                              tree=Depends(get_pack_tree)) -> PackSection:
    try:
        return await tree.lock_all_in_section(tenant, section_id)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e


async def _generate_question(request: Request, tenant: str, pack_id: str, question, worker, tree):
    """Draft one question with agentcore -- the SAME LLM path as /answers: build_tenant_worker()
    .answer() -> grounded generator + independent grounding critic + gate decision. kb_gap flips
    when nothing could be cited / grounding is zero. Locked questions are left untouched."""
    if question.locked:
        return question
    result = await worker.answer(question.req_id or question.id, question.text)
    grounding = round(result.critique.grounding, 2)
    return await tree.apply_generation(
        tenant, question.id, ai_answer=result.answer, ai_sources=result.citations,
        confidence=grounding, decision=result.decision.value,
        kb_gap=not result.citations or result.critique.grounding == 0)


@router.post("/{pack_id}/questions/{question_id}/generate")
async def generate_question(pack_id: str, question_id: str, request: Request,
                            tenant: str = Depends(authed_tenant),
                            _role: dict = Depends(require_role(Role.editor)),
                            packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)):
    await _require_pack(pack_id, tenant, packs)
    try:
        question = await tree.get_question(tenant, question_id)
    except PackQuestionNotFound as e:
        raise HTTPException(status_code=404, detail="question not found") from e
    pack = await packs.get(tenant, pack_id)
    worker = await build_tenant_worker(request, tenant, agent_id=pack.agent_id if pack else None)
    return await _generate_question(request, tenant, pack_id, question, worker, tree)


@router.post("/{pack_id}/sections/{section_id}/generate")
async def generate_section(pack_id: str, section_id: str, request: Request,
                           tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)),
                           packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> list:
    await _require_pack(pack_id, tenant, packs)
    try:
        section = await tree.get_section(tenant, section_id)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="section not found") from e
    if section.manual:
        return []
    pack = await packs.get(tenant, pack_id)
    worker = await build_tenant_worker(request, tenant, agent_id=pack.agent_id if pack else None)
    out = []
    for q in await tree.questions.list_for_section(tenant, section_id):
        out.append(await _generate_question(request, tenant, pack_id, q, worker, tree))
    return out


@router.post("/{pack_id}/generate")
async def generate_pack(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> list:
    """Whole-pack draft: every non-locked question in every non-manual section, via agentcore."""
    await _require_pack(pack_id, tenant, packs)
    pack = await packs.get(tenant, pack_id)
    worker = await build_tenant_worker(request, tenant, agent_id=pack.agent_id if pack else None)
    manual_sections = {s.id for s in await tree.sections.list(tenant, pack_id) if s.manual}
    out = []
    for q in await tree.questions.list(tenant, pack_id):
        if q.section_id in manual_sections:
            continue
        out.append(await _generate_question(request, tenant, pack_id, q, worker, tree))
    return out


@router.get("/{pack_id}/overview")
async def pack_overview(pack_id: str, tenant: str = Depends(authed_tenant),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> dict:
    """Cockpit header metrics: sections, AI-drafted X/Y, for-human-review, KB-sources counts."""
    await _require_pack(pack_id, tenant, packs)
    return await tree.overview(tenant, pack_id)
