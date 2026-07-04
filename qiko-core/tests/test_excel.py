import io

import pytest

from app.modules.agentcore.tools import ToolError
from app.modules.excel.service import ExcelService, build_excel_tools, workbook_to_records
from app.modules.knowledge.service import KnowledgeService


def _wb() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["region", "revenue"])
    ws.append(["EMEA", 120000])
    ws.append(["APAC", 90000])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_workbook_to_records():
    recs = workbook_to_records(_wb())
    assert any("region: EMEA" in r and "revenue: 120000" in r for r in recs)
    assert all(r.startswith("[Sales]") for r in recs)


async def test_store_and_search():
    svc = ExcelService(KnowledgeService())
    assert await svc.store_workbook("acme", "q3", _wb()) == 2
    hits = await svc.search("acme", "EMEA revenue")
    assert any("EMEA" in h for h in hits)


async def test_excel_tools():
    svc = ExcelService(KnowledgeService())
    reg = build_excel_tools(svc, "acme", _wb())
    assert reg.names() == ["search_data", "store_excel_data"]
    assert await reg.invoke("store_excel_data", {"source_name": "q3"}) == 2
    assert any("APAC" in h for h in await reg.invoke("search_data", {"query": "APAC"}))
    with pytest.raises(ToolError):
        await reg.invoke("search_data", {"query": ""})  # validated
