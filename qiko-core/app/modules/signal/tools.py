"""signal-mcp tool suite: the Qiko Signal engine's capabilities exposed as schema-validated
agentcore tools, fronting the Signal engine (thothgraph/qiko-signal). The agent PRESENTS engine
output; it never computes or alters scores (measurement firewall - see SCRUM-53)."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.modules.agentcore.tools import ToolRegistry


class SignalEngineGateway(Protocol):
    def create_project(self, tenant: str, brand: str, domain: str) -> dict: ...
    def run_scan(self, project_id: str) -> dict: ...
    def get_score(self, scan_id: str) -> dict: ...
    def get_buckets(self, scan_id: str) -> dict: ...
    def get_recommendations(self, scan_id: str) -> list[dict]: ...
    def export_pdf(self, scan_id: str) -> str: ...


class CreateProjectArgs(BaseModel):
    brand: str = Field(min_length=1)
    domain: str = Field(min_length=3)


class ScanArgs(BaseModel):
    project_id: str = Field(min_length=1)


class ScanIdArgs(BaseModel):
    scan_id: str = Field(min_length=1)


def build_signal_tools(gateway: SignalEngineGateway, tenant: str) -> ToolRegistry:
    reg = ToolRegistry()

    @reg.register("signal_create_project", CreateProjectArgs)
    def _create(a: CreateProjectArgs) -> dict:
        return gateway.create_project(tenant, a.brand, a.domain)

    @reg.register("signal_run_scan", ScanArgs)
    def _run(a: ScanArgs) -> dict:
        return gateway.run_scan(a.project_id)

    @reg.register("signal_get_score", ScanIdArgs)
    def _score(a: ScanIdArgs) -> dict:
        return gateway.get_score(a.scan_id)

    @reg.register("signal_get_buckets", ScanIdArgs)
    def _buckets(a: ScanIdArgs) -> dict:
        return gateway.get_buckets(a.scan_id)

    @reg.register("signal_get_recommendations", ScanIdArgs)
    def _recs(a: ScanIdArgs) -> list[dict]:
        return gateway.get_recommendations(a.scan_id)

    @reg.register("signal_export_pdf", ScanIdArgs)
    def _pdf(a: ScanIdArgs) -> str:
        return gateway.export_pdf(a.scan_id)

    return reg
