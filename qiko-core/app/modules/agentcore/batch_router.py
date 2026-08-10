"""Grounded batch answering + export -- a generic AgentCore capability (config over the engine,
not a new service). Powers requirement-answering workers like IDG: ask many questions at once,
get an answer + confidence + citations + human-review decision per item, export to xlsx."""
from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.core.deps import current_claims, WorkerRecheck, authed_tenant, require_role, resolve_tenant_worker
from app.modules.chat.files import build_xlsx
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/agents", tags=["agentcore"])

MAX_BATCH_QUESTIONS = 20
MAX_BATCH_QUESTION_CHARS = 4000
MAX_BATCH_TOTAL_CHARS = 20_000
BatchQuestion = Annotated[str, Field(min_length=1, max_length=MAX_BATCH_QUESTION_CHARS)]


class BatchAskBody(BaseModel):
    questions: list[BatchQuestion] = Field(min_length=1, max_length=MAX_BATCH_QUESTIONS)
    agent_id: str = Field(min_length=1)

    @field_validator("questions")
    @classmethod
    def enforce_total_question_budget(cls, questions: list[str]) -> list[str]:
        if sum(len(question) for question in questions) > MAX_BATCH_TOTAL_CHARS:
            raise ValueError("batch question text exceeds the aggregate limit")
        return questions


class BatchAnswer(BaseModel):
    id: str
    question: str
    answer: str
    confidence: float
    decision: str
    citations: list[str]


class FeedbackBody(BaseModel):
    requirement_id: str = Field(min_length=1)
    approved_text: str = Field(min_length=1)
    topic: str | None = None
    agent_id: str = Field(min_length=1)


async def _run_batch(request: Request, tenant: str,
                     body: BatchAskBody) -> tuple[list[BatchAnswer], WorkerRecheck]:
    worker, recheck = await resolve_tenant_worker(request, tenant, body.agent_id)
    out: list[BatchAnswer] = []
    for i, question in enumerate(body.questions):
        await recheck()
        result = await worker.answer(
            f"q{i + 1}", question, recheck_worker=recheck)
        await recheck()
        out.append(BatchAnswer(
            id=result.requirement_id, question=question, answer=result.answer,
            confidence=round(result.confidence, 2), decision=result.decision.value,
            citations=result.citations,
        ))
    await recheck()
    return out, recheck


@router.post("/batch-answer", response_model=list[BatchAnswer])
async def batch_answer(body: BatchAskBody, request: Request, tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor))) -> list[BatchAnswer]:
    """Answer a list of requirements/questions, each grounded + confidence-scored + gated.

    Editor-or-above: each question is a real LLM call (up to 200 per request), so a read-only
    viewer must not be able to run unbounded bulk generation."""
    answers, recheck = await _run_batch(request, tenant, body)
    await recheck()
    return answers


@router.post("/feedback")
async def feedback(body: FeedbackBody, request: Request,
                   claims: dict = Depends(current_claims),
                   tenant: str = Depends(authed_tenant),
                   _role: dict = Depends(require_role(Role.editor))) -> dict:
    """Human approves or edits an answer -> it becomes verified ground truth for that topic, so
    future answers are grounded in it instead of re-guessing (the same review->flywheel loop the
    original IDG worker used, now a generic capability every worker gets for free).

    Writes into the tenant's knowledge base, so it needs the same Editor-or-above bar as every
    other content-mutating endpoint -- a viewer role must not be able to plant "verified ground
    truth" that every future answer in the tenant gets grounded against."""
    worker, recheck = await resolve_tenant_worker(request, tenant, body.agent_id)
    await recheck()
    await worker.approve(
        body.requirement_id, body.approved_text, topic=body.topic,
        agent_id=body.agent_id, recheck_worker=recheck)
    await recheck()
    # verified_answers has a created_at and nothing else: no actor, no agent_id. So this row is the only
    # place that can answer "who decided this is what we say about this topic", which is the question
    # asked when a worker starts giving an answer nobody recognises.
    #
    # The approved text is NOT recorded. It is customer content, it is already durable in the knowledge
    # base, and copying it here would duplicate it into a store with a different retention and a
    # different erasure path. The character count is kept instead, because "approved 40 characters" and
    # "approved 4,000" are different acts.
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.ANSWER_APPROVED, target_id=body.requirement_id,
        target_label=body.topic or None, tenant_id=tenant, actor_type=audit.USER,
        actor_id=str(claims.get("sub") or ""), actor_label=str(claims.get("email") or ""),
        changes=audit.diff(audit_actions.ANSWER_APPROVED, {}, {
            "decision": "approved", "topic": body.topic or None,
            "characters": len(body.approved_text or "")}),
        metadata={"agent_id": body.agent_id, "source": "batch_review"}), request=request)
    return {"verified": True}


@router.post("/batch-export")
async def batch_export(body: BatchAskBody, request: Request, tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor))) -> StreamingResponse:
    """Same as batch-answer, downloadable as xlsx (Question/Answer/Confidence/Decision/Citations
    + a blank Feedback column, matching the coverage-report shape a reviewer fills in).

    Editor-or-above for the same reason as batch-answer: it runs a real LLM call per question."""
    answers, recheck = await _run_batch(request, tenant, body)
    await recheck()
    rows = [["#", "Question", "Answer", "Confidence", "Decision", "Citations", "Feedback"]]
    for a in answers:
        rows.append([a.id, a.question, a.answer, a.confidence, a.decision, " | ".join(a.citations), ""])
    xlsx_bytes = build_xlsx("Answers", rows)
    await recheck()
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=worker-answers.xlsx"},
    )
