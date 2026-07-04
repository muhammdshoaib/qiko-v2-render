"""Signal HTTP API (tenant-scoped). Fronts the Signal engine; the app only PRESENTS engine output
(measurement firewall). Engine client is a dev stub until the real HTTP client lands in SCRUM-59."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant

router = APIRouter(prefix="/signal", tags=["signal"])


def _engine(request: Request):
    return request.app.state.signal_engine


class CreateProjectBody(BaseModel):
    brand: str = Field(min_length=1)
    domain: str = Field(min_length=3)


class ScanBody(BaseModel):
    project_id: str = Field(min_length=1)


@router.post("/projects")
def create_project(body: CreateProjectBody, request: Request, tenant: str = Depends(authed_tenant)) -> dict:
    return _engine(request).create_project(tenant, body.brand, body.domain)


@router.post("/scan")
def run_scan(body: ScanBody, request: Request, _tenant: str = Depends(authed_tenant)) -> dict:
    return _engine(request).run_scan(body.project_id)


@router.get("/score/{scan_id}")
def score(scan_id: str, request: Request, _tenant: str = Depends(authed_tenant)) -> dict:
    return _engine(request).get_score(scan_id)


@router.get("/buckets/{scan_id}")
def buckets(scan_id: str, request: Request, _tenant: str = Depends(authed_tenant)) -> dict:
    return _engine(request).get_buckets(scan_id)


@router.get("/recommendations/{scan_id}")
def recommendations(scan_id: str, request: Request, _tenant: str = Depends(authed_tenant)) -> list[dict]:
    return _engine(request).get_recommendations(scan_id)


@router.post("/export/{scan_id}")
def export(scan_id: str, request: Request, _tenant: str = Depends(authed_tenant)) -> dict:
    return {"url": _engine(request).export_pdf(scan_id)}
