"""Finance vertical orchestration: upload -> parse -> store -> analyze; list/delete; analytics; chat.

Uses the same Protocol-based store injection as app.modules.sales_intelligence.service, defaulting
to in-memory stores for dev/tests and swappable for Postgres-backed stores (app/db/stores.py) via
app.state. The LLM provider is injected too, so tests use a deterministic stub with no network.

SECURITY (OWASP): upload() enforces a hard size cap and validates the bytes are a real .xlsx
(the parser raises FinanceParseError otherwise). The stored filename is sanitized so it can never
be used for path traversal (we never write it to disk, but we keep it clean for defence in depth).
Every store call is tenant + agent scoped (BOLA-safe).
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import re
import uuid
from dataclasses import dataclass

from app.modules.ai.gateway import LLMProvider, get_provider
from app.modules.finance.analytics import _month_label, compute_analytics
from app.modules.finance.chat import FinancialAnalystChat
from app.modules.finance.models import (
    DEFAULT_CURRENCY,
    FinanceChatMessage,
    FinanceChatStore,
    FinanceFile,
    FinanceFileStore,
    InMemoryFinanceChatStore,
    InMemoryFinanceFileStore,
)
from app.modules.finance.parser import ParseError, parse_workbook

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB cap, mirrors the frontend contract + main.py request cap
_HISTORY_LOOKBACK = 6  # messages (3 exchanges) fed back into the prompt for follow-up questions
ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/octet-stream",  # some browsers/clients send this for a file upload
    "application/zip",  # xlsx is a zip container; a few clients report it this way
    "",
}


class FinanceError(Exception):
    pass


class FinanceUploadError(FinanceError):
    """Bad upload (too large, wrong type, or unparseable)."""


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _safe_filename(name: str | None) -> str:
    """Never trust the client filename. Strip any path components + keep a safe basename so it can
    never traverse (`../`) or carry a path, even though we never write it to disk."""
    if not name:
        return "upload.xlsx"
    base = name.replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "upload.xlsx"
    return base[:255]


def _namespace_for(agent_id: str, file_id: str) -> str:
    return f"finance-{agent_id}-{file_id}"


_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_MONTH_NAMES = {name: i + 1 for i, name in enumerate([
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
])}
_FILENAME_PERIOD_RE = re.compile(
    # (?<![A-Za-z]) rather than \b: `_safe_filename` turns spaces into underscores, and `_` is a
    # \w character, so a plain \b would not separate "_February" (no letter/non-letter transition)
    # -- but it must still reject "SummaryMay_2026" matching "May" mid-word. A negative lookbehind
    # for a letter accepts "_"/"-"/space/digit/start-of-string before the month, and rejects only
    # another letter immediately before it. The separator is optional ([_\-\s]*, not +) so a
    # concatenated "September2026" (no punctuation between month and year at all) still matches.
    r"(?<![A-Za-z])(" + "|".join(_MONTH_NAMES) + r")[_\-\s]*(\d{4})", re.IGNORECASE)
_MIN_PLAUSIBLE_YEAR, _MAX_PLAUSIBLE_YEAR = 2000, 2100  # sanity bound so an unrelated 4-digit
# number next to a month-like substring (e.g. a reference/serial code) can't fabricate a bogus,
# wildly-out-of-range period -- exactly the class of bug this whole fix removes, just inverted.


def _file_declared_month(file: FinanceFile) -> str | None:
    """The single "YYYY-MM" period a workbook's own name declares, e.g.
    "Touchstone_Income_and_Exp_February_2026.xlsx" -> "2026-02", or
    "..._YTD_December_2025.xlsx" -> "2025-12" (the "YTD" prefix is just skipped over).

    EL-1021/EL-1024: a real "YTD" workbook can carry individual invoices going back years
    (arrears, historic maintenance records) alongside its current reporting period, so deriving
    a file's period from its row-level transaction dates (the original EL-1014 fix) made a single
    upload's period span a decade or more. This client's exports consistently name each file after
    the one period it actually reports on, so that name -- not the rows inside it -- is the
    reliable source for "what period does this upload represent". Returns None when a name has no
    recognizable month/year (the caller should treat that as "this file declares no period", not
    fall back to guessing from its data)."""
    for name in (file.source_name, file.file_name):
        if not name:
            continue
        match = None
        for m in _FILENAME_PERIOD_RE.finditer(name):
            year = int(m.group(2))
            if _MIN_PLAUSIBLE_YEAR <= year <= _MAX_PLAUSIBLE_YEAR:
                match = m  # keep the last (rightmost) plausible match, e.g. skips a leading
                           # "YTD_" prefix or a trailing "(1)"/"(5)" copy tag
        if match:
            return f"{int(match.group(2)):04d}-{_MONTH_NAMES[match.group(1).lower()]:02d}"
    return None


def _resolve_range(frm: str | None, to: str | None,
                   month: str | None) -> tuple[str | None, str | None]:
    """The FE date filter can arrive as an explicit from/to window OR as a single `month`
    ("YYYY-MM"). When only a month is given, expand it to that month's inclusive ISO range so the
    analytics date filter (which compares ISO YYYY-MM-DD strings) narrows to exactly that month.
    An explicit from/to always wins; a malformed month is ignored (treated as no filter)."""
    if month and not frm and not to:
        m = _MONTH_RE.match(month.strip())
        if m:
            year, mon = int(m.group(1)), int(m.group(2))
            if 1 <= mon <= 12:
                last = calendar.monthrange(year, mon)[1]
                return f"{month}-01", f"{month}-{last:02d}"
    return frm, to


def _available_months(files: list[FinanceFile]) -> list[str]:
    """Distinct "YYYY-MM" periods declared by the uploaded files, used to populate the dashboard's
    month filter (EL-1014) and the Financial Chat's reported date range (EL-1024). One entry per
    file (see _file_declared_month) -- not per transaction row, and not from
    FinanceFile.uploaded_at: a workbook can cover any period regardless of when it happens to be
    uploaded, and a YTD workbook's own row dates can span years of arrears/historic records well
    outside the one period the file itself represents (EL-1021)."""
    months = {m for f in files if (m := _file_declared_month(f))}
    return sorted(months)


@dataclass
class FinanceService:
    files: FinanceFileStore = None  # type: ignore[assignment]
    chats: FinanceChatStore = None  # type: ignore[assignment]
    provider: LLMProvider = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.files is None:
            self.files = InMemoryFinanceFileStore()
        if self.chats is None:
            self.chats = InMemoryFinanceChatStore()
        if self.provider is None:
            self.provider = get_provider()

    async def upload(self, tenant: str, agent_id: str, data: bytes, *, filename: str | None = None,
                     content_type: str | None = None, source_name: str | None = None,
                     currency: str = DEFAULT_CURRENCY) -> FinanceFile:
        if not data:
            raise FinanceUploadError("empty upload")
        if len(data) > MAX_UPLOAD_BYTES:
            raise FinanceUploadError("file exceeds the 10MB limit")
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct not in ALLOWED_CONTENT_TYPES:
            raise FinanceUploadError("unsupported content type; upload an .xlsx workbook")

        try:
            expenses, incomes = parse_workbook(data)
        except ParseError as e:
            raise FinanceUploadError(str(e)) from e

        file_id = _new_id()
        safe_name = _safe_filename(filename)
        row_count = len(expenses) + len(incomes)
        file = FinanceFile(
            id=file_id, tenant=tenant, agent_id=agent_id, file_name=safe_name,
            source_name=(source_name or safe_name).strip()[:255] or safe_name,
            namespace=_namespace_for(agent_id, file_id), size_bytes=len(data), row_count=row_count,
            currency=currency, expense_rows=[e.to_dict() for e in expenses],
            income_rows=[i.to_dict() for i in incomes])
        return await self.files.add(file)

    async def list_files(self, tenant: str, agent_id: str) -> dict:
        files = await self.files.list_for_agent(tenant, agent_id)
        return {
            "id": agent_id,
            "files": [{
                "id": f.id, "label": f.source_name or f.file_name, "namespace": f.namespace,
                "rowCount": f.row_count, "uploadedAt": f.uploaded_at,
            } for f in files],
            "totalFiles": len(files),
            "totalRows": sum(f.row_count for f in files),
            "availableMonths": _available_months(files),
        }

    async def delete_files(self, tenant: str, agent_id: str, ids: list[str]) -> dict:
        deleted = await self.files.delete(tenant, agent_id, ids)
        return {
            "success": True, "deleted": deleted, "deletedCount": len(deleted),
            "message": f"{len(deleted)} file(s) deleted successfully.",
        }

    async def analytics(self, tenant: str, agent_id: str, *, frm: str | None = None,
                        to: str | None = None, month: str | None = None) -> dict:
        no_filter = not frm and not to and not month
        frm, to = _resolve_range(frm, to, month)
        files = await self.files.list_for_agent(tenant, agent_id)
        expenses: list = []
        incomes: list = []
        for f in files:
            expenses.extend(f.expenses())
            incomes.extend(f.incomes())
        currency = files[0].currency if files else DEFAULT_CURRENCY
        result = compute_analytics(expenses, incomes, frm=frm, to=to, currency=currency)
        # EL-1024: with no month filter, compute_analytics falls back to the earliest/latest
        # *transaction* date across every row for its reported dateRange. A YTD workbook's real
        # data can span years of arrears well outside the period it was actually uploaded for
        # (EL-1021), so that fallback let the Financial Analyst chat claim a decade-plus range for
        # a portfolio that only ever had a couple of months uploaded. Report the files' own
        # declared periods instead; the totals above are untouched, still summed over every row.
        #
        # If not one uploaded file's name carries a recognizable period, blank the range out
        # rather than silently falling through to compute_analytics's row-scan value above: that
        # fallback is exactly the multi-year-spread bug this fix exists to remove, so resurrecting
        # it here (even only for the rare all-unrecognizable-names case) would defeat the fix.
        if no_filter and files:
            months = _available_months(files)
            if months:
                last_year, last_month = (int(p) for p in months[-1].split("-"))
                range_from = f"{months[0]}-01"
                range_to = f"{months[-1]}-{calendar.monthrange(last_year, last_month)[1]:02d}"
                result["dateRange"] = {
                    "from": range_from, "to": range_to,
                    "label": _month_label(range_from, range_to),
                }
            else:
                logger.warning(
                    "finance.dateRange.no_declared_period tenant=%s agent_id=%s file_count=%d",
                    tenant, agent_id, len(files))
                result["dateRange"] = {"from": "", "to": "", "label": ""}
        result["files"] = [{"label": f.source_name or f.file_name, "namespace": f.namespace,
                            "rowCount": f.row_count} for f in files]
        result["totalFiles"] = len(files)
        result["totalRows"] = sum(f.row_count for f in files)
        return result

    async def chat(self, tenant: str, agent_id: str, message: str,
                   recheck_worker=None) -> dict:
        message = (message or "").strip()
        if not message:
            raise FinanceError("message is required")
        async def recheck() -> None:
            if recheck_worker is not None:
                await recheck_worker()

        await recheck()
        analytics = await self.analytics(tenant, agent_id)
        # Fetch the prior turns before this exchange is stored, so a follow-up ("why do you say
        # that") can resolve against what was actually asked/answered (EL-1003).
        prior = await self.chats.list_for_agent(tenant, agent_id, limit=_HISTORY_LOOKBACK)
        history = [{"role": m.role, "content": m.content} for m in prior]
        # Offload the (synchronous, network-bound) LLM call to a thread so it doesn't block the
        # event loop -- same pattern the rfp router uses for its provider calls.
        try:
            result = await asyncio.to_thread(
                FinancialAnalystChat(self.provider).answer, message, analytics, history)
        finally:
            await recheck()
        user = FinanceChatMessage(
            id=_new_id(), tenant=tenant, agent_id=agent_id,
            role="user", content=message)
        assistant = FinanceChatMessage(
            id=_new_id(), tenant=tenant, agent_id=agent_id,
            role="assistant", content=result["reply"])
        await self.chats.add_exchange(tenant, agent_id, user, assistant)
        await recheck()
        return result

    async def history(self, tenant: str, agent_id: str, limit: int = 100) -> dict:
        messages = await self.chats.list_for_agent(tenant, agent_id, limit=limit)
        return {
            "id": agent_id, "count": len(messages),
            "history": [{"role": m.role, "content": m.content,
                         "timestamp": int(m.created_at.timestamp() * 1000)} for m in messages],
        }

    async def clear_history(self, tenant: str, agent_id: str) -> dict:
        cleared = await self.chats.clear(tenant, agent_id)
        return {"success": True, "id": agent_id,
                "message": f"Cleared {cleared} message(s)."}
