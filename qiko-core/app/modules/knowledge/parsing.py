"""Multi-format document text extraction for knowledge ingestion.

Turns an uploaded file (PDF/DOCX/CSV/XLSX/JSON/JSONL/TXT/MD) into normalised plain text ready for
chunk -> embed. Heavy binary readers are isolated per format so the ingestion pipeline stays
format-agnostic. Unsupported types are rejected (no silent empty ingest).
"""
from __future__ import annotations

import csv
import io
import json
import re

SUPPORTED = {"txt", "md", "csv", "json", "jsonl", "pdf", "docx", "xlsx", "xls"}


class UnsupportedDocumentError(Exception):
    pass


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _read_text(data: bytes) -> str:
    return data.decode("utf-8", "ignore")


def _read_csv(data: bytes) -> str:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8", "ignore"))))
    return "\n".join(", ".join(cell for cell in row) for row in rows if any(row))


def _json_to_text(obj, prefix: str = "") -> str:
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lines.append(_json_to_text(v, f"{prefix}{k}: "))
    elif isinstance(obj, list):
        for item in obj:
            lines.append(_json_to_text(item, prefix))
    else:
        lines.append(f"{prefix}{obj}")
    return "\n".join(x for x in lines if x)


def _read_json(data: bytes) -> str:
    return _json_to_text(json.loads(data.decode("utf-8", "ignore")))


def _read_jsonl(data: bytes) -> str:
    out = []
    for line in data.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if line:
            out.append(_json_to_text(json.loads(line)))
    return "\n".join(out)


def _read_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _read_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts: list[str] = []
    for ws in wb.worksheets:
        parts.append(f"# {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                parts.append(", ".join(cells))
    return "\n".join(parts)


def _read_pdf(data: bytes) -> str:  # pragma: no cover - exercised via integration (binary PDF)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


_EXTRACTORS = {
    "txt": _read_text, "md": _read_text, "csv": _read_csv,
    "json": _read_json, "jsonl": _read_jsonl,
    "docx": _read_docx, "xlsx": _read_xlsx, "xls": _read_xlsx, "pdf": _read_pdf,
}


def extract_text(filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _EXTRACTORS:
        raise UnsupportedDocumentError(f"unsupported document type: .{ext or '?'}")
    return normalize_text(_EXTRACTORS[ext](data))
