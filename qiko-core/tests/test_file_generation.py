import io

import pytest
from openpyxl import load_workbook

from app.modules.chat.files import (
    FileGenerator,
    UnsupportedFormatError,
    build_csv,
    build_docx,
    build_pdf,
    build_xlsx,
)


def test_builders_produce_valid_artifacts():
    assert build_csv([["a", "b"], [1, 2]]) == b"a,b\r\n1,2\r\n"
    assert build_xlsx("S", [["h"], ["v"]])[:2] == b"PK"        # xlsx = zip
    assert build_docx("Title", ["para"])[:2] == b"PK"          # docx = zip
    assert build_pdf("Title", ["line one", "line two"])[:5] == b"%PDF-"


@pytest.mark.parametrize("value", ["=1+1", "+SUM(1,1)", "-1+2", "@SUM(1,1)", "\t=1"])
def test_xlsx_formula_capable_strings_are_literal(value):
    workbook = load_workbook(io.BytesIO(build_xlsx("S", [[value, -10]])), data_only=False)
    cell = workbook.active["A1"]
    assert cell.data_type != "f"
    assert cell.value == "'" + value
    assert workbook.active["B1"].value == -10


def test_generate_stores_tenant_scoped_and_returns_key():
    gen = FileGenerator()
    key = gen.generate("acme", "docx", "bid", {"title": "Bid", "paragraphs": ["We hold ISO 9001."]})
    assert key.startswith("acme/exports/") and key.endswith("-bid.docx")
    stored = gen.storage.get("acme", key)
    assert stored[:2] == b"PK"  # retrievable, valid docx


def test_unsupported_format_rejected():
    with pytest.raises(UnsupportedFormatError):
        FileGenerator().generate("acme", "exe", "x", {})
