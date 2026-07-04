import io
import json

import pytest

from app.modules.knowledge.parsing import (
    UnsupportedDocumentError,
    extract_text,
    normalize_text,
)


def test_normalize_collapses_whitespace():
    assert normalize_text("a  \t b\r\n\n\n\nc  ") == "a b\n\nc"


def test_txt_and_md():
    assert extract_text("notes.txt", b"hello world") == "hello world"
    assert extract_text("r.md", b"# Title\n\ntext") == "# Title\n\ntext"


def test_csv():
    out = extract_text("d.csv", b"name,role\nAda,owner\nBob,viewer\n")
    assert "name, role" in out and "Ada, owner" in out


def test_json_and_jsonl():
    out = extract_text("d.json", json.dumps({"company": "IDG", "certs": ["ISO 9001"]}).encode())
    assert "company: IDG" in out and "ISO 9001" in out
    jl = b'{"q": "a"}\n{"q": "b"}\n'
    assert "q: a" in extract_text("d.jsonl", jl) and "q: b" in extract_text("d.jsonl", jl)


def test_docx_real_extraction():
    from docx import Document

    doc = Document()
    doc.add_paragraph("IDG holds ISO 9001 certification.")
    buf = io.BytesIO()
    doc.save(buf)
    assert "ISO 9001 certification" in extract_text("bid.docx", buf.getvalue())


def test_xlsx_real_extraction():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Certs"
    ws.append(["standard", "valid_until"])
    ws.append(["ISO 9001", 2027])
    buf = io.BytesIO()
    wb.save(buf)
    out = extract_text("certs.xlsx", buf.getvalue())
    assert "# Certs" in out and "ISO 9001, 2027" in out


def test_unsupported_type_rejected():
    with pytest.raises(UnsupportedDocumentError):
        extract_text("malware.exe", b"MZ")
