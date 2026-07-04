from app.modules.chat.files import FileGenerator
from app.modules.excel.analytics import compute_analytics, export_report


def test_compute_analytics_numeric_aggregations():
    rows = [["region", "revenue"], ["EMEA", 120000], ["APAC", 90000], ["AMER", 60000]]
    a = compute_analytics(rows)
    assert a["row_count"] == 3
    rev = a["columns"]["revenue"]
    assert rev["sum"] == 270000 and rev["max"] == 120000 and rev["min"] == 60000
    assert rev["avg"] == 90000.0
    assert "region" not in a["columns"]  # non-numeric column excluded


def test_compute_analytics_empty():
    assert compute_analytics([])["row_count"] == 0


def test_export_report_xlsx_and_pdf_stored():
    gen = FileGenerator()
    analytics = compute_analytics([["region", "revenue"], ["EMEA", 120000], ["APAC", 90000]])
    xlsx_key = export_report(gen, "acme", "q3", analytics, fmt="xlsx")
    pdf_key = export_report(gen, "acme", "q3", analytics, fmt="pdf")
    assert xlsx_key.startswith("acme/exports/") and xlsx_key.endswith(".xlsx")
    assert gen.storage.get("acme", xlsx_key)[:2] == b"PK"     # valid xlsx
    assert gen.storage.get("acme", pdf_key)[:5] == b"%PDF-"   # valid pdf
