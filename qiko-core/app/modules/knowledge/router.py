"""Knowledge HTTP API (tenant-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.core.deps import current_claims, authed_tenant, get_knowledge, require_role, resolve_tenant_worker
from app.modules.identity.rbac import Role
from app.modules.knowledge.evaluation import RFP_CRITERIA, evaluate_document
from app.modules.knowledge.parsing import MAX_UPLOAD_BYTES, UnsupportedDocumentError
from app.modules.workers.worker import StubProviderUnavailable

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Cap free-text ingest so a single request can't push an unbounded payload through chunk -> embed.
_MAX_INGEST_TEXT = 2 * 1024 * 1024  # 2 MB of text


# agent_id scopes knowledge to a single worker (QIK-315). For ingest it remains optional so
# callers can still create shared tenant-wide knowledge; search requires it so the endpoint can
# never read across worker corpora. Both are always within the authed tenant (team-shared).
class IngestBody(BaseModel):
    doc_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=_MAX_INGEST_TEXT)
    agent_id: str | None = Field(default=None, min_length=1, max_length=64)


class SearchBody(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    agent_id: str = Field(min_length=1, max_length=64)


@router.post("/ingest")
async def ingest(body: IngestBody, tenant: str = Depends(authed_tenant),
                 _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_knowledge)) -> dict:
    return {"doc_id": body.doc_id,
            "chunks": await svc.ingest(tenant, body.doc_id, body.text, agent_id=body.agent_id)}


@router.post("/search")
async def search(body: SearchBody, tenant: str = Depends(authed_tenant), svc=Depends(get_knowledge)) -> dict:
    return {"results": [p.text for p in await svc.retrieve(tenant, body.query, k=body.k, agent_id=body.agent_id)]}


@router.get("/documents")
async def documents(tenant: str = Depends(authed_tenant), agent_id: str | None = None,
                    svc=Depends(get_knowledge)) -> list[dict]:
    return await svc.list_documents(tenant, agent_id=agent_id)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request,
                          claims: dict = Depends(current_claims),
                          tenant: str = Depends(authed_tenant), agent_id: str | None = None,
                          _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_knowledge)) -> dict:
    """Delete every passage belonging to a document.

    Not recoverable from within the product: the source file is not retained, so the only remedy is
    for the customer to find and re-upload it. It also silently degrades retrieval for every worker
    that was grounding answers in it, which is the failure the customer notices first and attributes to
    the AI rather than to a deletion.

    The passage COUNT is what makes the row worth having. "A document was deleted" is a fact nobody
    disputes; "3,412 passages were removed from the corpus" is the one that explains why answers got
    worse on a particular day.
    """
    removed = await svc.delete_document(tenant, doc_id, agent_id=agent_id)
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.DOCUMENT_DELETED, target_id=doc_id, tenant_id=tenant,
        actor_type=audit.USER, actor_id=str(claims.get("sub") or ""),
        actor_label=str(claims.get("email") or ""),
        reason=request.headers.get("x-audit-reason"),
        changes=audit.diff(audit_actions.DOCUMENT_DELETED, {},
                           {"doc_id": doc_id, "passages_removed": removed}),
        metadata={"agent_id": agent_id}), request=request)
    return {"removed": removed}


@router.post("/ingest-file")
async def ingest_file(file: UploadFile = File(...), doc_id: str = Form(...),
                      agent_id: str | None = Form(None),
                      tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_knowledge)) -> dict:
    # Read with a hard cap so a huge upload can't exhaust memory (defence beyond the global
    # request-size middleware), mirroring finance.router.upload.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds the 10MB limit")
    try:
        chunks = await svc.ingest_file(tenant, doc_id, file.filename or doc_id, data, agent_id=agent_id)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"doc_id": doc_id, "chunks": chunks}


@router.get("/rfp-criteria")
def rfp_criteria(_tenant: str = Depends(authed_tenant)) -> dict:
    return {"criteria": RFP_CRITERIA}


class EvaluateBody(BaseModel):
    doc_id: str = Field(min_length=1)
    criterion: str = Field(min_length=1)
    topic: str | None = None
    agent_id: str = Field(min_length=1)


@router.post("/evaluate")
async def evaluate(body: EvaluateBody, request: Request, tenant: str = Depends(authed_tenant),
                   _role: dict = Depends(require_role(Role.editor)),
                   svc=Depends(get_knowledge)) -> dict:
    worker, recheck = await resolve_tenant_worker(request, tenant, body.agent_id)
    await recheck()
    agent = worker.agent  # agentcore (grounded + gated)
    result = await evaluate_document(
        agent, svc, tenant, body.doc_id, body.criterion,
        topic=body.topic, recheck_worker=recheck)
    if result.stub:
        raise StubProviderUnavailable
    await recheck()
    return {"decision": result.decision.value, "answer": result.answer, "grounding": result.critique.grounding}
