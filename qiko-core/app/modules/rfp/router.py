"""RFP pack HTTP API (tenant-scoped): create/list/get/delete tenders a worker is answering."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_rfp_packs, require_role
from app.modules.identity.rbac import Role
from app.modules.rfp.service import RfpPack, RfpPackNotFound

router = APIRouter(prefix="/rfp/packs", tags=["rfp"])


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


@router.delete("/{pack_id}")
async def delete_pack(pack_id: str, tenant: str = Depends(authed_tenant),
                      _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_rfp_packs)) -> dict:
    await svc.delete(tenant, pack_id)
    return {"deleted": pack_id}
