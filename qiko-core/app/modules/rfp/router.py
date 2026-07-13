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
from app.modules.rfp.extraction import ExtractionError, extract_requirements
from app.modules.rfp.service import CachedAnswer, PackRequirement, RfpPack, RfpPackNotFound

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
                    _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs)) -> RfpPack:
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
                      reqs=Depends(get_requirements), answers=Depends(get_pack_answers)) -> dict:
    await answers.delete_for_pack(tenant, pack_id)
    await reqs.delete_for_pack(tenant, pack_id)
    await svc.delete(tenant, pack_id)
    return {"deleted": pack_id}


@router.post("/{pack_id}/extract")
async def extract(pack_id: str, file: UploadFile = File(...), tenant: str = Depends(authed_tenant),
                  _role: dict = Depends(require_role(Role.editor)), packs=Depends(get_rfp_packs),
                  reqs=Depends(get_requirements), answers=Depends(get_pack_answers)) -> list[PackRequirement]:
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

    try:
        # extract_requirements() blocks on a synchronous LLM call -- run it off the event loop
        # thread so a slow tender document doesn't freeze every other request this process is
        # serving for the whole duration (this took down preprod once already).
        extracted = await asyncio.to_thread(extract_requirements, text, get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Persisted so /ask can ground follow-up questions in the source document later, without
    # re-uploading it.
    await packs.set_document_text(tenant, pack_id, text)
    # A new extraction can rewrite req_ids/content entirely -- drop any cached answers from a
    # previous extraction so the cockpit doesn't show drafts for stale requirements.
    await answers.delete_for_pack(tenant, pack_id)
    return await reqs.save_extracted(tenant, pack_id, extracted)


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


_STATUS_LABELS = {"auto_accept": "AI-drafted (met internal bar)", "human_review": "AI-drafted, for human review"}


_ANSWER_CONCURRENCY = 4  # bounded so a 15-section tender doesn't fire 15 simultaneous LLM calls


async def _answer_pack(request: Request, tenant: str, pack_id: str, reqs, answers, *,
                       force: bool = False) -> list[dict]:
    """Answer every KB requirement in the pack, backed by a Postgres cache (rfp_pack_answers) so a
    15-section tender isn't re-drafted (each section a real LLM call) on every page visit -- only
    the first time, or when force=True (the cockpit's per-section Regenerate action)."""
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
    return list(await asyncio.gather(*(answer_one(r) for r in requirements)))


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
                      reqs=Depends(get_requirements), answers=Depends(get_pack_answers)) -> list[dict]:
    """JSON form of the same answer-pack pipeline the exports use -- powers the tender cockpit's
    Sections tab (AI draft + confidence/grounding + citations + status per requirement).
    force=true bypasses the cache and re-drafts every KB requirement (Regenerate all) -- a real
    LLM call per requirement, so (unlike the plain cached read) it needs Editor-or-above, not just
    any authenticated viewer, to avoid unbounded regeneration cost from a read-only role."""
    if force and not role_allows(claims.get("role", "viewer"), Role.editor):
        raise HTTPException(status_code=403, detail="insufficient role to regenerate answers")
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers, force=force)
    return [{
        "req_id": a["req"].req_id, "req_title": a["req"].title, "classification": a["req"].classification,
        "requirement": a["req"].requirement, "answer": a["answer"], "confidence": a["confidence"],
        "grounding": a["confidence"], "status": a["decision"], "citations": a["citations"], "note": a["note"],
    } for a in answered]


@router.get("/{pack_id}/export/xlsx")
async def export_xlsx(pack_id: str, request: Request, tenant: str = Depends(authed_tenant),
                      reqs=Depends(get_requirements), answers=Depends(get_pack_answers)) -> StreamingResponse:
    """Coverage sheet: one row per requirement, with a Grounding % column and human-readable
    status, plus blank Review/Comment columns for offline reviewer sign-off."""
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers)
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
                            reqs=Depends(get_requirements), answers=Depends(get_pack_answers)) -> StreamingResponse:
    """Client-ready submission: per-section heading + answer prose only, no confidence/citation
    annotations. Un-drafted (non-KB) sections show a placeholder for the team to complete."""
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers)
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
                             reqs=Depends(get_requirements), answers=Depends(get_pack_answers)) -> StreamingResponse:
    """Internal annotated variant: requirement text + confidence/status note + answer + KB
    sources -- for human review before the clean submission is finalised."""
    answered = await _answer_pack(request, tenant, pack_id, reqs, answers)
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
