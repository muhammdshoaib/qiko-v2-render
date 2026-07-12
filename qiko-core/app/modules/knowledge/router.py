"""Knowledge HTTP API (tenant-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, build_tenant_worker, get_knowledge
from app.modules.knowledge.evaluation import RFP_CRITERIA, evaluate_document

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class IngestBody(BaseModel):
    doc_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SearchBody(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)


@router.post("/ingest")
async def ingest(body: IngestBody, tenant: str = Depends(authed_tenant), svc=Depends(get_knowledge)) -> dict:
    return {"doc_id": body.doc_id, "chunks": await svc.ingest(tenant, body.doc_id, body.text)}


@router.post("/search")
async def search(body: SearchBody, tenant: str = Depends(authed_tenant), svc=Depends(get_knowledge)) -> dict:
    return {"results": [p.text for p in await svc.retrieve(tenant, body.query, k=body.k)]}


@router.get("/documents")
async def documents(tenant: str = Depends(authed_tenant), svc=Depends(get_knowledge)) -> list[dict]:
    return await svc.list_documents(tenant)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_knowledge)) -> dict:
    return {"removed": await svc.delete_document(tenant, doc_id)}


@router.post("/ingest-file")
async def ingest_file(file: UploadFile = File(...), doc_id: str = Form(...),
                      tenant: str = Depends(authed_tenant), svc=Depends(get_knowledge)) -> dict:
    data = await file.read()
    chunks = await svc.ingest_file(tenant, doc_id, file.filename or doc_id, data)
    return {"doc_id": doc_id, "chunks": chunks}


@router.get("/rfp-criteria")
def rfp_criteria(_tenant: str = Depends(authed_tenant)) -> dict:
    return {"criteria": RFP_CRITERIA}


class EvaluateBody(BaseModel):
    doc_id: str = Field(min_length=1)
    criterion: str = Field(min_length=1)
    topic: str | None = None
    agent_id: str | None = None


@router.post("/evaluate")
async def evaluate(body: EvaluateBody, request: Request, tenant: str = Depends(authed_tenant),
                   svc=Depends(get_knowledge)) -> dict:
    worker = await build_tenant_worker(request, tenant, agent_id=body.agent_id)
    agent = worker.agent  # agentcore (grounded + gated)
    result = await evaluate_document(agent, svc, tenant, body.doc_id, body.criterion, topic=body.topic)
    return {"decision": result.decision.value, "answer": result.answer, "grounding": result.critique.grounding}
