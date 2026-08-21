"""Finance vertical HTTP API -- tenant-scoped, per-agent.

Route shape follows qiko-core's per-agent module convention (see app.modules.sales_intelligence.
router): `/finance/{agent_id}/...` under the `/api/v1` prefix. It supersedes the external
excel-agent-server surface consumed by qiko-frontend ELApi.ts (POST /api/upload, GET /api/files,
POST /api/user/files/delete, GET /api/user, POST /api/chat, GET/DELETE /api/history).

All endpoints are tenant-scoped via `authed_tenant` (BOLA-safe -- tenant comes from the verified
access-token claims, never a client header). Mutations (upload/delete/chat) require the editor
role. Uploads are validated for content-type + size before parsing (OWASP: untrusted file input).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.core.deps import current_claims, authed_tenant, require_role, resolve_tenant_worker
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.finance.schemas import (
    FinanceAnalyticsResponse, FinanceChatResponse, FinanceClearHistoryResponse,
    FinanceDeleteResponse, FinanceFilesResponse, FinanceHistoryResponse, FinanceUploadResponse,
)
from app.modules.finance.service import MAX_UPLOAD_BYTES, FinanceError, FinanceUploadError
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/finance", tags=["finance"])


def get_finance(request: Request):
    return request.app.state.finance


async def _resolve_worker(request: Request, tenant: str, agent_id: str):
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    return recheck


@router.post("/{agent_id}/upload", status_code=201, response_model=FinanceUploadResponse)
async def upload(agent_id: str, request: Request, file: UploadFile = File(...),
                 title: str | None = Form(default=None),
                 description: str | None = Form(default=None),  # noqa: ARG001 -- accepted, not stored as data
                 tenant: str = Depends(authed_tenant), _role: dict = Depends(require_role(Role.editor)),
                 svc=Depends(get_finance)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    # Read with a hard cap so a huge upload can't exhaust memory (defence beyond the global
    # request-size middleware). Filename is never trusted -- the service sanitizes it.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds the 10MB limit")
    try:
        stored = await svc.upload(tenant, agent_id, data, filename=file.filename,
                                  content_type=file.content_type, source_name=title)
    except FinanceUploadError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await recheck()
    return {
        "fileName": stored.file_name, "sourceName": stored.source_name, "size": stored.size_bytes,
        "namespace": stored.namespace, "totalRows": stored.row_count, "indexed": True,
        "recordsStored": stored.row_count,
    }


@router.get("/{agent_id}/files", response_model=FinanceFilesResponse)
async def files(agent_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_finance)) -> dict:
    return await svc.list_files(tenant, agent_id)


class DeleteFilesBody(BaseModel):
    ids: list[str] | str = Field(...)


@router.delete("/{agent_id}/files", response_model=FinanceDeleteResponse)
async def delete_files(agent_id: str, body: DeleteFilesBody, request: Request,
                       claims: dict = Depends(current_claims),
                       tenant: str = Depends(authed_tenant),
                       _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_finance)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    ids = body.ids if isinstance(body.ids, list) else [body.ids]
    ids = [str(i).strip() for i in ids if str(i).strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="at least one file id is required")
    result = await svc.delete_files(tenant, agent_id, ids)
    await recheck()
    # Financial records, deleted in bulk by an id list. The ids are recorded rather than the filenames:
    # a filename can carry a client name, and the id is what identifies the record for a restore.
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.FINANCE_FILES_DELETED, target_id=agent_id, tenant_id=tenant,
        actor_type=audit.USER, actor_id=str(claims.get("sub") or ""),
        actor_label=str(claims.get("email") or ""),
        changes=audit.diff(audit_actions.FINANCE_FILES_DELETED, {}, {"file_count": len(ids)}),
        metadata={"file_ids": ids[:50]}), request=request)
    return result


@router.get("/{agent_id}/analytics", response_model=FinanceAnalyticsResponse)
async def analytics(agent_id: str, request: Request, tenant: str = Depends(authed_tenant),
                    svc=Depends(get_finance)) -> dict:
    frm = request.query_params.get("from")
    to = request.query_params.get("to")
    # The FE date filter can arrive as an explicit from/to window OR a single `month` ("YYYY-MM"),
    # which the service expands to that month's inclusive range (explicit from/to wins).
    month = request.query_params.get("month")
    return await svc.analytics(tenant, agent_id, frm=frm, to=to, month=month)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post("/{agent_id}/chat", response_model=FinanceChatResponse)
async def chat(agent_id: str, body: ChatBody, request: Request,
               tenant: str = Depends(authed_tenant),
               _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_finance)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    try:
        result = await svc.chat(
            tenant, agent_id, body.message, recheck_worker=recheck)
        await recheck()
        return result
    except FinanceError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{agent_id}/history", response_model=FinanceHistoryResponse)
async def history(agent_id: str, limit: int = 100, tenant: str = Depends(authed_tenant),
                  svc=Depends(get_finance)) -> dict:
    return await svc.history(tenant, agent_id, limit=max(1, min(200, limit)))


@router.delete("/{agent_id}/history", response_model=FinanceClearHistoryResponse)
async def clear_history(agent_id: str, request: Request,
                        tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_finance)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    result = await svc.clear_history(tenant, agent_id)
    await recheck()
    return result
