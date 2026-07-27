"""Request-free RFP tender-artifact generation, shared by the HTTP routes and the background job.

Uploading a tender kicks off a BACKGROUND job (app.tasks.jobs.generate_tender_artifacts) that
produces and persists ALL artifacts -- Requirements, Sections, the Tender Brief, the Compliance
checklist and per-section grounded draft answers -- so the upload endpoint returns immediately and
the frontend polls a per-artifact status. This module holds the pieces that must run identically
whether invoked inline from a route or off the request path on a worker, so there is no request
object and no FastAPI HTTPException in here (routes translate the domain errors below).

gen_status contract (persisted on RfpPack.gen_status, polled via GET /rfp/packs/{id}/status):

    {
      "requirements": "pending" | "running" | "ready" | "error",
      "sections":     "pending" | "running" | "ready" | "error",
      "brief":        "pending" | "running" | "ready" | "error",
      "compliance":   "pending" | "running" | "ready" | "error",
      "drafts": {"state": "pending|running|ready|partial|error", "done": int, "total": int,
                 "failed": int, "failed_ids": [str]},
      "updated_at": ISO-8601 string,
      "error": null | string,        # the LATEST stage error (kept for back-compat)
      "errors": {stage: message},    # per-stage error detail, so a poller can attribute each
    }

The drafts stage isolates a per-question failure: one question raising does NOT abort the rest.
It fails closed only on a StubProviderUnavailable (a genuine provider outage). Any other question
error is counted (drafts.failed / failed_ids) and the loop continues, so the stage ends "ready"
(no failures) or "partial" (some failed). The stage is also resumable/idempotent: it skips
questions that already have a draft, so an arq retry after a worker restart resumes rather than
re-drafting from zero.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from app.core.deps import assemble_worker
from app.modules.agentcore.models import Decision
from app.modules.ai.gateway import get_provider
from app.modules.rfp.brief import extract_brief
from app.modules.rfp.compliance import extract_compliance
from app.modules.rfp.extraction import (
    MAX_CONTEXT_CHARS,
    MAX_ITEMS,
    ExtractionError,
    chunk_document,
    ensure_unique_codes,
    extract_requirements,
)
from app.modules.workers.worker import StubProviderUnavailable

# extract/brief/compliance are one-shot calls over a whole tender document (tens of thousands of
# chars in, a full structured response out) -- the gateway's default read_timeout (20s) is tuned
# for the fast per-requirement answering hot path and is routinely too tight for these. A single
# near-160k-char extraction (mid-size docs that don't chunk) can take well over 90s, so give these
# document-scale calls a generous ceiling.
_DOCUMENT_READ_TIMEOUT = 180
_EXTRACT_CONCURRENCY = 4  # bounded so a huge tender doesn't fire a dozen simultaneous LLM calls

logger = logging.getLogger(__name__)


def _consolidate(items: list[dict]) -> list[dict]:
    """Dedupe/merge the chunked-fallback's per-chunk sections into a small COARSE catalogue and cap
    it at MAX_ITEMS TOP-LEVEL sections. Overlapping chunks (and a section straddling a boundary)
    surface the same top-level section more than once; we merge by normalised title so the section
    tree still lands ~10-20 top-level sections rather than dozens. The first occurrence of a title
    wins for the section's own fields, but a duplicate's `subsections` are UNIONED into it (by
    normalised sub-section title) so no sub-requirement seen in only one chunk is lost."""
    out: list[dict] = []
    by_title: dict[str, dict] = {}

    def _key(title: str) -> str:
        return re.sub(r"\s+", " ", (title or "").strip().lower())

    for item in items:
        key = _key(item.get("title"))
        existing = by_title.get(key) if key else None
        if existing is None:
            merged = dict(item)
            merged["subsections"] = list(item.get("subsections") or [])
            out.append(merged)
            if key:
                by_title[key] = merged
            continue
        # merge this duplicate's sub-sections into the first occurrence, deduped by title
        seen = {_key(s.get("title")) for s in existing["subsections"]}
        for sub in item.get("subsections") or []:
            sub_key = _key(sub.get("title"))
            if sub_key and sub_key in seen:
                continue
            if sub_key:
                seen.add(sub_key)
            existing["subsections"].append(sub)
    # Two chunks can each surface a section with the SAME model id but a DIFFERENT title (so the
    # title-keyed merge above keeps both). Re-uniquify the codes here so the merged catalogue never
    # has two top-level sections sharing a code (and colliding sub-section req_ids).
    return ensure_unique_codes(out[:MAX_ITEMS])


async def extract_requirements_chunked(text: str) -> list[dict]:
    """Produce the COARSE requirements catalogue for a tender.

    For a typical document (<= MAX_CONTEXT_CHARS = 160k) do ONE extraction call over the whole
    text, capped at MAX_ITEMS (~20) coarse top-level sections -- exactly like idg-worker's
    requirements_extractor. A single 160k input with a small (<=20-item) completion finishes well
    within the document read-timeout, so this does NOT reintroduce the Bedrock read-timeout problem
    that motivated chunking.

    Chunking is only a FALLBACK for very large documents (> 160k): each chunk extracts in parallel,
    then the merged result is consolidated (deduped/merged by title) and capped to <= MAX_ITEMS so
    a huge tender still yields a coarse ~15-section tree, not 80."""
    if len(text) <= MAX_CONTEXT_CHARS:
        return await asyncio.to_thread(extract_requirements, text,
                                       get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT),
                                       max_chars=MAX_CONTEXT_CHARS)

    chunks = chunk_document(text)
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
    merged = _consolidate([item for chunk_items in results for item in chunk_items])
    if not merged:
        raise ExtractionError("no requirements could be extracted from this document")
    return merged


async def generate_question(tenant: str, question, worker, tree):
    """Draft one question with agentcore -- the SAME LLM path as /answers: worker.answer() ->
    grounded generator + independent grounding critic + gate decision. kb_gap flips when nothing
    could be cited OR the answer could not be grounded confidently (the gate escalated to human
    review, i.e. grounding below the accept threshold) -- this is the "KB gap" signal shown in the
    cockpit, matching the validated idg behaviour. Locked questions are left untouched. Raises
    StubProviderUnavailable (never persists) if the answer came from the StubProvider fallback."""
    if question.locked:
        return question
    result = await worker.answer(question.req_id or question.id, question.text)
    if result.stub:
        raise StubProviderUnavailable()
    # confidence (the writer's self-report) and grounding (the independent critic) are now
    # DISTINCT values; persist both plus the writer's gaps note. kb_gap keeps its meaning: no
    # citations OR the gate escalated to human review.
    return await tree.apply_generation(
        tenant, question.id, ai_answer=result.answer, ai_sources=result.citations,
        confidence=round(result.confidence, 2), grounding=round(result.critique.grounding, 2),
        gaps=result.gaps, decision=result.decision.value,
        kb_gap=not result.citations or result.decision == Decision.human_review)


def initial_gen_status() -> dict:
    """All-pending status, written by the upload endpoint before the background job starts so the
    frontend can begin polling immediately."""
    return {
        "requirements": "pending",
        "sections": "pending",
        "brief": "pending",
        "compliance": "pending",
        "drafts": {"state": "pending", "done": 0, "total": 0, "failed": 0, "failed_ids": []},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "errors": {},
    }


def _touch(status: dict) -> dict:
    status["updated_at"] = datetime.now(timezone.utc).isoformat()
    return status


def _stage_error(status: dict, stage: str, message: str) -> None:
    """Record a stage failure both as the latest `error` (back-compat) AND under `errors[stage]`,
    so a poller can tell WHICH stage failed instead of the single field clobbering the others."""
    status["error"] = message
    status.setdefault("errors", {})[stage] = message


async def run_generation(*, tenant: str, pack_id: str, agent_id: str | None,
                         packs, reqs, answers, tree, knowledge, agents, sessionmaker=None) -> dict:
    """Produce and persist every tender artifact, updating gen_status after each stage so a poller
    sees progress. Each stage is independent: a failure marks that stage "error" and the pipeline
    continues (except the drafts stub-guard, which stops without persisting)."""
    status = initial_gen_status()

    async def save() -> None:
        await packs.set_gen_status(tenant, pack_id, _touch(status))

    pack = await packs.get(tenant, pack_id)
    if pack is None:
        return status
    document_text = pack.document_text or ""

    # --- Stage 1: requirements + sections (one extraction feeds both) -----------------------
    status["requirements"] = status["sections"] = "running"
    await save()
    try:
        extracted = await extract_requirements_chunked(document_text)
        # A fresh extraction can rewrite req_ids/content entirely -- drop any cached answers so the
        # cockpit doesn't show drafts for stale requirements, then rebuild the section tree.
        await answers.delete_for_pack(tenant, pack_id)
        await tree.populate_from_extraction(tenant, pack_id, extracted)
        await reqs.save_extracted(tenant, pack_id, extracted)
        status["requirements"] = status["sections"] = "ready"
    except Exception as e:  # noqa: BLE001 - one stage failing must not sink the others
        status["requirements"] = status["sections"] = "error"
        _stage_error(status, "requirements", str(e))
    await save()

    # --- Stage 2: tender brief ---------------------------------------------------------------
    status["brief"] = "running"
    await save()
    try:
        brief = await asyncio.to_thread(extract_brief, document_text,
                                        get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
        await packs.set_brief(tenant, pack_id, brief)
        status["brief"] = "ready"
    except Exception as e:  # noqa: BLE001
        status["brief"] = "error"
        _stage_error(status, "brief", str(e))
    await save()

    # --- Stage 3: compliance checklist -------------------------------------------------------
    status["compliance"] = "running"
    await save()
    try:
        items = await asyncio.to_thread(extract_compliance, document_text,
                                        get_provider(read_timeout=_DOCUMENT_READ_TIMEOUT))
        await packs.set_compliance(tenant, pack_id, items)
        status["compliance"] = "ready"
    except Exception as e:  # noqa: BLE001
        status["compliance"] = "error"
        _stage_error(status, "compliance", str(e))
    await save()

    # --- Stage 4: per-section grounded draft answers -----------------------------------------
    # Per-item isolated, resumable and idempotent: skip questions that ALREADY have a draft (so an
    # arq retry after a worker restart resumes rather than re-drafting), draft each remaining one
    # under its own try/except so one failure isolates that item (counted in `failed`) instead of
    # aborting the rest, and fail closed only on a genuine provider outage (StubProviderUnavailable).
    status["drafts"] = {"state": "running", "done": 0, "total": 0, "failed": 0, "failed_ids": []}
    await save()
    try:
        worker = await assemble_worker(sessionmaker=sessionmaker, agents=agents,
                                       knowledge=knowledge, tenant=tenant, agent_id=agent_id)
        manual_sections = {s.id for s in await tree.sections.list(tenant, pack_id) if s.manual}
        questions = [q for q in await tree.questions.list(tenant, pack_id)
                     if q.section_id not in manual_sections and not q.locked]
        total = len(questions)
        pending = [q for q in questions if not (q.ai_answer or q.user_draft)]
        done = total - len(pending)  # resume point: questions already drafted on a prior run
        failed = 0
        failed_ids: list[str] = []
        status["drafts"] = {"state": "running", "done": done, "total": total,
                            "failed": 0, "failed_ids": []}
        await save()
        for q in pending:
            try:
                await generate_question(tenant, q, worker, tree)
            except StubProviderUnavailable:
                raise  # a genuine outage: fail closed (handled below), never persist a stub
            except Exception as e:  # noqa: BLE001 - one bad question must not sink the rest
                failed += 1
                failed_ids.append(q.req_id or q.id)
                status["drafts"]["failed"] = failed
                status["drafts"]["failed_ids"] = failed_ids
                logger.warning("drafts: question %s (section %s) failed to draft: %s",
                               q.id, q.section_id, e)
            else:
                done += 1
                status["drafts"]["done"] = done
            await save()
        status["drafts"]["state"] = "ready" if failed == 0 else "partial"
    except StubProviderUnavailable:
        # Fail closed: surface the outage, persist nothing further, and stop drafting.
        status["drafts"]["state"] = "error"
        _stage_error(status, "drafts", "answer generation is temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        status["drafts"]["state"] = "error"
        _stage_error(status, "drafts", str(e))
    await save()
    return status
