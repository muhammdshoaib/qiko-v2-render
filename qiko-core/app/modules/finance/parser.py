"""Parse an uploaded property-portfolio .xlsx into normalized income + expense rows.

A faithful Python port of the sheet/column detection in qiko-mcp-parser src/analyzer.ts
(findSheet / rowsToExpenses / rowsToIncomes), reading via openpyxl (already a qiko-core dep --
see app.modules.excel.service.workbook_to_records) instead of the Node `xlsx` library.

SECURITY (OWASP): the caller (service.py) enforces content-type + a 10MB size cap before we ever
touch the bytes. openpyxl itself rejects non-xlsx junk (InvalidFileException / BadZipFile), which
the service maps to a 422. Cell content is treated purely as data here -- never executed, never
interpolated into a query. Column headers/values are matched against a fixed allowlist of
candidate names; unknown columns are ignored.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime

# --- scalar coercion helpers (port of num/str/textOnly/parseDate) ----------------------------

_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DMY_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$")
# Excel's day-zero epoch (1899-12-30) so a serial like 45000 maps to a real date.
_EXCEL_EPOCH = datetime(1899, 12, 30)


def _num(v: object) -> float:
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        cleaned = re.sub(r"[,\s]", "", v)
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def _str(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _text_only(v: object) -> str:
    """Free-text identifier fields (vendor, descriptions): a purely-numeric value is almost
    certainly a mis-picked numeric column, not a name."""
    s = _str(v)
    if not s or _NUMERIC_RE.match(s):
        return ""
    return s


def _excel_serial_to_iso(v: object) -> str:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return ""
    try:
        d = _EXCEL_EPOCH.fromordinal(_EXCEL_EPOCH.toordinal() + int(v))
        return d.date().isoformat()
    except (ValueError, OverflowError):
        return ""


def _dmy_to_iso(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    m = _DMY_RE.match(s)
    if not m:
        return ""
    return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"


def _parse_date(v: object) -> str:
    # openpyxl with data_only=True yields real datetime/date objects for date-typed cells.
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    iso = _excel_serial_to_iso(v)
    if iso:
        return iso
    return _dmy_to_iso(v)


# --- sheet + column matching (port of findSheet / EXPENSE_COLS / INCOME_COLS) -----------------

_EXPENSE_SHEETS = ["Exp YTD", "Exp", "Expenditure", "Expenses", "Expenses YTD", "Expenditure YTD"]
_INCOME_SHEETS = [
    "Income Receivable YTD", "Income Receivable", "Income receivable", "Income YTD", "Income",
    "Receivable", "Receivables",
]

EXPENSE_COLS = {
    "property_ref": ["Property Reference", "Property Ref", "Property", "Prop Ref"],
    "property_desc": ["Property Description", "Prop Desc", "Property Name", "Prop Name"],
    "heading": ["Heading", "Category", "Type", "Cost Type", "Expense Type"],
    "vendor": ["Supname", "Supplier Name", "Vendor Name", "Vendor"],
    "nett": ["Nett", "Net", "Net Amount", "Net Value"],
    "vat": ["Vat", "VAT", "Tax", "VAT Amount"],
    "gross": ["Gross", "Gross Amount", "Total", "Amount", "Gross Value"],
    "exp_date": ["Exp date", "Expense Date", "Exp Date", "Date", "Inv date", "Invoice Date"],
    "unit_ref": ["Unit Reference", "Unit Ref", "Unit", "UnitRef"],
    "unit_desc": ["Unit Description", "Unit Desc", "Unit Name"],
    "fixflo_ref": ["FixFlo Reference", "FixFlo Ref", "FixFlo", "Fixflo Reference"],
    "supplier_ref": ["Supplier ref.", "Supplier Ref", "Sup Ref", "Supplier Code"],
    "expenditure_desc": ["Expenditure Description", "Exp Description", "Expense Description", "Work Description"],
    "period_from": ["Period[1]", "Period From", "Period Start"],
    "period_to": ["Period[2]", "Period To", "Period End"],
    "settled": ["Settled[1]", "Settled", "Paid", "Payment Status"],
}

INCOME_COLS = {
    "unit_ref": ["Unit Ref", "Unit Reference", "UnitRef", "Tenant Ref", "TenantRef", "Tenant Reference"],
    "unit_desc": ["Unit Description", "Unit Desc", "Unit"],
    "property_ref": ["Property Reference", "Property Ref"],
    "amount": ["Amount[1]", "Amount", "Value", "Charge Amount", "Demanded"],
    "income_receivable": ["Income Receivable", "Outstanding", "Receivable", "Balance"],
    "tran_date": ["Tran date", "Transaction Date", "Date", "Charge Date"],
}


def _norm_key(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\[(\d+)\]", r"\1", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _normalize_sheet_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def _find_sheet(wb, candidates: list[str]):
    sheet_map = {_normalize_sheet_name(name): name for name in wb.sheetnames}
    for cand in candidates:
        actual = sheet_map.get(_normalize_sheet_name(cand))
        if actual:
            return wb[actual]
    # Fuzzy: every significant word of a candidate must appear in the sheet name.
    for cand in candidates:
        words = [w for w in _normalize_sheet_name(cand).split(" ") if w and w != "ytd"]
        if not words:
            continue
        for norm_name, actual in sheet_map.items():
            if all(w in norm_name for w in words):
                return wb[actual]
    return None


def _sheet_to_rows(ws) -> list[dict]:
    """Header-aware: first non-empty row is the header; each subsequent row -> {header: value}."""
    all_rows = list(ws.iter_rows(values_only=True))
    if not all_rows:
        return []
    header = [str(c).strip() if c is not None else "" for c in all_rows[0]]
    out: list[dict] = []
    for row in all_rows[1:]:
        record: dict = {}
        for i, value in enumerate(row):
            if i < len(header) and header[i]:
                record[header[i]] = value
        if record:
            out.append(record)
    return out


def _normalize_row(row: dict) -> dict:
    return {_norm_key(k): v for k, v in row.items()}


def _pick(row: dict, candidates: list[str]) -> object:
    for c in candidates:
        v = row.get(_norm_key(c))
        if v is not None and v != "":
            return v
    for c in candidates:
        norm_c = _norm_key(c)
        for k, v in row.items():
            if norm_c in k and v is not None and v != "":
                return v
    return None


def _pick_exact(row: dict, candidates: list[str]) -> object:
    for c in candidates:
        v = row.get(_norm_key(c))
        if v is not None and v != "":
            return v
    return None


# --- row -> domain --------------------------------------------------------------------------

def rows_to_expenses(raw_rows: list[dict]):
    from app.modules.finance.models import ExpenseRow

    out = []
    for raw in raw_rows:
        r = _normalize_row(raw)
        property_ref = _str(_pick(r, EXPENSE_COLS["property_ref"]))
        unit_ref = _str(_pick(r, EXPENSE_COLS["unit_ref"]))
        if not property_ref and unit_ref:
            slash = unit_ref.find("/")
            property_ref = unit_ref[:slash] if slash > 0 else unit_ref
        if not property_ref:
            continue
        prop_desc = _pick(r, EXPENSE_COLS["property_desc"])
        if prop_desc is None or prop_desc == "":
            prop_desc = _pick_exact(r, ["Desc", "Description"])
        out.append(ExpenseRow(
            property_ref=property_ref, property_desc=_str(prop_desc),
            heading=_str(_pick(r, EXPENSE_COLS["heading"])), vendor=_text_only(_pick(r, EXPENSE_COLS["vendor"])),
            nett=_num(_pick(r, EXPENSE_COLS["nett"])), vat=_num(_pick(r, EXPENSE_COLS["vat"])),
            gross=_num(_pick(r, EXPENSE_COLS["gross"])), exp_date=_parse_date(_pick(r, EXPENSE_COLS["exp_date"])),
            unit_ref=unit_ref, unit_desc=_str(_pick(r, EXPENSE_COLS["unit_desc"])),
            fixflo_ref=_str(_pick(r, EXPENSE_COLS["fixflo_ref"])),
            supplier_ref=_str(_pick(r, EXPENSE_COLS["supplier_ref"])),
            expenditure_desc=_str(_pick(r, EXPENSE_COLS["expenditure_desc"])),
            period_from=_dmy_to_iso(_pick(r, EXPENSE_COLS["period_from"])),
            period_to=_dmy_to_iso(_pick(r, EXPENSE_COLS["period_to"])),
            settled=_str(_pick(r, EXPENSE_COLS["settled"])),
        ))
    return out


def rows_to_incomes(raw_rows: list[dict]):
    from app.modules.finance.models import IncomeRow

    out = []
    for raw in raw_rows:
        r = _normalize_row(raw)
        unit_ref = _str(_pick(r, INCOME_COLS["unit_ref"]))
        property_ref = _str(_pick(r, INCOME_COLS["property_ref"]))
        if not property_ref:
            if not unit_ref:
                continue
            property_ref = unit_ref[:7]
        out.append(IncomeRow(
            property_ref=property_ref, unit_ref=unit_ref, unit_desc=_str(_pick(r, INCOME_COLS["unit_desc"])),
            amount=_num(_pick(r, INCOME_COLS["amount"])),
            income_receivable=_num(_pick(r, INCOME_COLS["income_receivable"])),
            tran_date=_parse_date(_pick(r, INCOME_COLS["tran_date"])),
        ))
    return out


class ParseError(ValueError):
    """Raised when the uploaded bytes are not a readable .xlsx workbook."""


def parse_workbook(data: bytes):
    """Parse .xlsx bytes -> (expense_rows, income_rows). Raises ParseError on non-xlsx input."""
    import zipfile

    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, OSError, ValueError, KeyError) as e:
        raise ParseError("uploaded file is not a valid .xlsx workbook") from e

    try:
        exp_sheet = _find_sheet(wb, _EXPENSE_SHEETS)
        inc_sheet = _find_sheet(wb, _INCOME_SHEETS)
        expenses = rows_to_expenses(_sheet_to_rows(exp_sheet)) if exp_sheet is not None else []
        incomes = rows_to_incomes(_sheet_to_rows(inc_sheet)) if inc_sheet is not None else []
    finally:
        wb.close()
    return expenses, incomes
