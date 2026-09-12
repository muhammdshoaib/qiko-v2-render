"""Live contract and playground for a tenant's worker API (JM2-1134).

The contract is generated from the running application, so it cannot document a version that
is not deployed. That is the whole reason this exists: the committed mirror in
joseph-mews-api-docs had no mechanism to notice it had fallen behind, and an integrating team
lost time building against it.

Auth reuses require_worker_caller from the joseph_mews module rather than introducing a
second scheme. That dependency is the authorisation boundary for this whole worker surface,
and documentation of a surface should not be easier to reach than the surface itself.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.modules.agents.service import Agent
from app.modules.api_docs.environments import ENVIRONMENTS
from app.modules.api_docs.shell import render
from app.modules.api_docs.spec_filter import TENANT_SPECS, filter_spec
from app.modules.joseph_mews.router import require_worker_caller

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["api-docs"])


@router.get("/openapi.json")
async def tenant_openapi(
    tenant_id: str,
    request: Request,
    _caller: Annotated[Agent | None, Depends(require_worker_caller)],
) -> dict:
    document = filter_spec(request.app.openapi(), tenant_id)
    if document is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no documented worker surface for that tenant")
    return document


@router.get("/docs", response_class=HTMLResponse)
async def tenant_docs(tenant_id: str) -> HTMLResponse:
    """Unauthenticated by necessity, harmless by construction: see shell.render's docstring.
    The tenant check happens here too, so the page cannot be used to discover which tenants
    exist."""
    if tenant_id not in TENANT_SPECS:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no documented worker surface for that tenant")
    return HTMLResponse(render(tenant_id, ENVIRONMENTS))
