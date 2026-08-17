"""Per-agent Intelligence Worker HTTP API -- tenant-scoped, read-only catalog skeleton.

This is the vertical skeleton for milestone 2: it exposes the source catalog and a verify
endpoint. Connection storage, credential encryption, and scheduled sync come in milestone 3.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, require_role, resolve_tenant_worker
from app.modules.identity.rbac import Role
from app.modules.intelligence.catalog import SourceCatalog, UnknownSource

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class VerifySourceBody(BaseModel):
    config: dict = Field(default_factory=dict)
    credential: str = Field(default="")


def get_source_catalog(request: Request) -> SourceCatalog:
    return request.app.state.intelligence_catalog


async def _resolve_worker(request: Request, tenant: str, agent_id: str):
    """Confirm the agent belongs to the tenant and return the post-call recheck hook."""
    _worker, recheck = await resolve_tenant_worker(request, tenant, agent_id)
    return recheck


@router.get("/agents/{agent_id}/sources")
async def list_sources(agent_id: str, request: Request,
                       tenant: str = Depends(authed_tenant),
                       catalog: SourceCatalog = Depends(get_source_catalog)) -> list[dict]:
    await _resolve_worker(request, tenant, agent_id)
    return catalog.items(connected=set())


@router.get("/agents/{agent_id}/sources/{key}")
async def get_source(agent_id: str, key: str, request: Request,
                     tenant: str = Depends(authed_tenant),
                     catalog: SourceCatalog = Depends(get_source_catalog)) -> dict:
    await _resolve_worker(request, tenant, agent_id)
    definition = catalog.definition(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="source not found")
    return {
        "key": definition.key,
        "name": definition.name,
        "description": definition.description,
        "pollable": definition.pollable,
        "connected": False,
    }


@router.post("/agents/{agent_id}/sources/{key}/verify")
async def verify_source(agent_id: str, key: str, body: VerifySourceBody, request: Request,
                        tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)),
                        catalog: SourceCatalog = Depends(get_source_catalog)) -> dict:
    recheck = await _resolve_worker(request, tenant, agent_id)
    try:
        connector = catalog.connector_for(key)
    except UnknownSource as e:
        raise HTTPException(status_code=404, detail="source not found") from e
    result = await connector.verify(config=body.config, credential=body.credential)
    await recheck()
    return result
