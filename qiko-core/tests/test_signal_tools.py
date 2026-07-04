import pytest

from app.modules.agentcore.tools import ToolError
from app.modules.signal.tools import build_signal_tools


class FakeEngine:
    def create_project(self, tenant, brand, domain):
        return {"project_id": "p1", "brand": brand, "domain": domain}

    def run_scan(self, project_id):
        return {"scan_id": "s1", "project_id": project_id, "status": "queued"}

    def get_score(self, scan_id):
        return {"scan_id": scan_id, "score": 72}

    def get_buckets(self, scan_id):
        return {"scan_id": scan_id, "buckets": {"answerability": 80, "comparison": 65}}

    def get_recommendations(self, scan_id):
        return [{"priority": "high", "text": "Add FAQ schema"}]

    def export_pdf(self, scan_id):
        return f"acme/exports/{scan_id}-signal.pdf"


def _reg():
    return build_signal_tools(FakeEngine(), "acme")


def test_signal_tools_registered():
    assert _reg().names() == [
        "signal_create_project", "signal_export_pdf", "signal_get_buckets",
        "signal_get_recommendations", "signal_get_score", "signal_run_scan"]


async def test_signal_tool_flow():
    reg = _reg()
    proj = await reg.invoke("signal_create_project", {"brand": "IDG", "domain": "idg.example"})
    scan = await reg.invoke("signal_run_scan", {"project_id": proj["project_id"]})
    assert (await reg.invoke("signal_get_score", {"scan_id": scan["scan_id"]}))["score"] == 72
    assert "answerability" in (await reg.invoke("signal_get_buckets", {"scan_id": "s1"}))["buckets"]
    assert (await reg.invoke("signal_get_recommendations", {"scan_id": "s1"}))[0]["priority"] == "high"
    assert (await reg.invoke("signal_export_pdf", {"scan_id": "s1"})).endswith(".pdf")


async def test_signal_args_validated():
    with pytest.raises(ToolError):
        await _reg().invoke("signal_create_project", {"brand": "IDG", "domain": "x"})  # domain too short
