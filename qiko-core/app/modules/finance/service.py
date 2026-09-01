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
import re
import uuid
from dataclasses import dataclass

from app.modules.ai.gateway import LLMProvider, get_provider
from app.modules.finance.analytics import compute_analytics
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
    """Distinct "YYYY-MM" months with real income or expense data across every uploaded file,
    used to populate the dashboard's month filter (EL-1014). This must come from the parsed
    transaction dates, not from FinanceFile.uploaded_at: a workbook can cover any period regardless
    of when it happens to be uploaded, and two workbooks uploaded together used to collapse to at
    most one (wrong) month option because they shared an upload timestamp."""
    months: set[str] = set()
    for f in files:
        for e in f.expenses():
            d = (e.period_to or e.exp_date)[:7]
            if _MONTH_RE.match(d):
                months.add(d)
        for i in f.incomes():
            d = i.tran_date[:7]
            if _MONTH_RE.match(d):
                months.add(d)
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
        frm, to = _resolve_range(frm, to, month)
        files = await self.files.list_for_agent(tenant, agent_id)
        expenses: list = []
        incomes: list = []
        for f in files:
            expenses.extend(f.expenses())
            incomes.extend(f.incomes())
        currency = files[0].currency if files else DEFAULT_CURRENCY
        result = compute_analytics(expenses, incomes, frm=frm, to=to, currency=currency)
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
