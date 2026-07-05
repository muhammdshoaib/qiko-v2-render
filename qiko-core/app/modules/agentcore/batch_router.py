"""Grounded batch answering + export -- a generic AgentCore capability (config over the engine,
not a new service). Powers requirement-answering workers like IDG: ask many questions at once,
get an answer + confidence + citations + human-review decision per item, export to xlsx."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, build_tenant_worker
from app.modules.chat.files import build_xlsx

router = APIRouter(prefix="/agents", tags=["agentcore"])


class BatchAskBody(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=200)


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


async def _run_batch(request: Request, tenant: str, body: BatchAskBody) -> list[BatchAnswer]:
    worker = build_tenant_worker(request, tenant)
    out: list[BatchAnswer] = []
    for i, question in enumerate(body.questions):
        result = await worker.answer(f"q{i + 1}", question)
        out.append(BatchAnswer(
            id=result.requirement_id, question=question, answer=result.answer,
            confidence=round(result.critique.grounding, 2), decision=result.decision.value,
            citations=result.citations,
        ))
    return out


@router.post("/batch-answer", response_model=list[BatchAnswer])
async def batch_answer(body: BatchAskBody, request: Request, tenant: str = Depends(authed_tenant)) -> list[BatchAnswer]:
    """Answer a list of requirements/questions, each grounded + confidence-scored + gated."""
    return await _run_batch(request, tenant, body)


@router.post("/feedback")
async def feedback(body: FeedbackBody, request: Request, tenant: str = Depends(authed_tenant)) -> dict:
    """Human approves or edits an answer -> it becomes verified ground truth for that topic, so
    future answers are grounded in it instead of re-guessing (the same review->flywheel loop the
    original IDG worker used, now a generic capability every worker gets for free)."""
    worker = build_tenant_worker(request, tenant)
    await worker.approve(body.requirement_id, body.approved_text, topic=body.topic)
    return {"verified": True}


@router.post("/batch-export")
async def batch_export(body: BatchAskBody, request: Request, tenant: str = Depends(authed_tenant)) -> StreamingResponse:
    """Same as batch-answer, downloadable as xlsx (Question/Answer/Confidence/Decision/Citations
    + a blank Feedback column, matching the coverage-report shape a reviewer fills in)."""
    answers = await _run_batch(request, tenant, body)
    rows = [["#", "Question", "Answer", "Confidence", "Decision", "Citations", "Feedback"]]
    for a in answers:
        rows.append([a.id, a.question, a.answer, a.confidence, a.decision, " | ".join(a.citations), ""])
    xlsx_bytes = build_xlsx("Answers", rows)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=worker-answers.xlsx"},
    )
