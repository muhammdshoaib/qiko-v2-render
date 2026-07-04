"""Excel HTTP API (tenant-scoped): NL search over ingested spreadsheet data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_excel, get_file_generator
from app.modules.excel.analytics import compute_analytics, export_report

router = APIRouter(prefix="/excel", tags=["excel"])


class ExcelSearchBody(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)


@router.post("/search")
async def search(body: ExcelSearchBody, tenant: str = Depends(authed_tenant), svc=Depends(get_excel)) -> dict:
    return {"results": await svc.search(tenant, body.query, k=body.k)}


@router.post("/upload")
async def upload(file: UploadFile = File(...), source_name: str = Form(...),
                 tenant: str = Depends(authed_tenant), svc=Depends(get_excel)) -> dict:
    records = await svc.store_workbook(tenant, source_name, await file.read())
    return {"source_name": source_name, "records": records}


class AnalyticsBody(BaseModel):
    rows: list[list]


@router.post("/analytics")
def analytics(body: AnalyticsBody, _tenant: str = Depends(authed_tenant)) -> dict:
    return compute_analytics(body.rows)


class ReportBody(BaseModel):
    source: str = Field(min_length=1)
    analytics: dict
    fmt: str = "xlsx"


@router.post("/report")
def report(body: ReportBody, tenant: str = Depends(authed_tenant), gen=Depends(get_file_generator)) -> dict:
    return {"key": export_report(gen, tenant, body.source, body.analytics, fmt=body.fmt)}
