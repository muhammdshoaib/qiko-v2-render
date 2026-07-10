"""Leads HTTP API (public capture, tenant-scoped for storage)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import get_leads, authed_tenant
from app.modules.leads.service import LeadError

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadBody(BaseModel):
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    payload: dict = {}


@router.post("")
async def capture(body: LeadBody, tenant: str = Depends(authed_tenant), svc=Depends(get_leads)) -> dict:
    try:
        lead = await svc.capture(tenant, body.kind, body.name, body.email, body.payload)
        return {"kind": lead.kind, "email": lead.email}
    except LeadError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
