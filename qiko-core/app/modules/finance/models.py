"""Domain dataclasses + store protocols for the Finance vertical.

Mirrors app.modules.sales_intelligence.models: dataclass + Protocol + in-memory default store,
swappable for a Postgres-backed store behind the same protocol (see app/db/stores.py).

Tables (see alembic 0016_finance / app/db/models.py):
 - finance_files          -> FinanceFile (one uploaded workbook + its parsed income/expense rows)
 - finance_chat_messages  -> FinanceChatMessage (Financial Analyst chat turns)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

DEFAULT_CURRENCY = "GBP"
CHAT_ROLES = ("user", "assistant")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ExpenseRow:
    """One normalized expenditure line from an uploaded workbook (an "Exp"/"Expenditure" sheet)."""
    property_ref: str
    property_desc: str = ""
    heading: str = ""
    vendor: str = ""
    nett: float = 0.0
    vat: float = 0.0
    gross: float = 0.0
    exp_date: str = ""
    unit_ref: str = ""
    unit_desc: str = ""
    fixflo_ref: str = ""
    supplier_ref: str = ""
    expenditure_desc: str = ""
    period_from: str = ""
    period_to: str = ""
    settled: str = ""

    def to_dict(self) -> dict:
        return {
            "propertyRef": self.property_ref, "propertyDesc": self.property_desc, "heading": self.heading,
            "vendor": self.vendor, "nett": self.nett, "vat": self.vat, "gross": self.gross,
            "expDate": self.exp_date, "unitRef": self.unit_ref, "unitDesc": self.unit_desc,
            "fixFloRef": self.fixflo_ref, "supplierRef": self.supplier_ref,
            "expenditureDesc": self.expenditure_desc, "periodFrom": self.period_from,
            "periodTo": self.period_to, "settled": self.settled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ExpenseRow:
        return cls(
            property_ref=str(d.get("propertyRef", "")), property_desc=str(d.get("propertyDesc", "")),
            heading=str(d.get("heading", "")), vendor=str(d.get("vendor", "")),
            nett=float(d.get("nett", 0) or 0), vat=float(d.get("vat", 0) or 0),
            gross=float(d.get("gross", 0) or 0), exp_date=str(d.get("expDate", "")),
            unit_ref=str(d.get("unitRef", "")), unit_desc=str(d.get("unitDesc", "")),
            fixflo_ref=str(d.get("fixFloRef", "")), supplier_ref=str(d.get("supplierRef", "")),
            expenditure_desc=str(d.get("expenditureDesc", "")), period_from=str(d.get("periodFrom", "")),
            period_to=str(d.get("periodTo", "")), settled=str(d.get("settled", "")),
        )


@dataclass
class IncomeRow:
    """One normalized income line from an uploaded workbook (an "Income Receivable" sheet)."""
    property_ref: str
    unit_ref: str = ""
    unit_desc: str = ""
    amount: float = 0.0
    income_receivable: float = 0.0
    tran_date: str = ""

    def to_dict(self) -> dict:
        return {
            "propertyRef": self.property_ref, "unitRef": self.unit_ref, "unitDesc": self.unit_desc,
            "amount": self.amount, "incomeReceivable": self.income_receivable, "tranDate": self.tran_date,
        }

    @classmethod
    def from_dict(cls, d: dict) -> IncomeRow:
        return cls(
            property_ref=str(d.get("propertyRef", "")), unit_ref=str(d.get("unitRef", "")),
            unit_desc=str(d.get("unitDesc", "")), amount=float(d.get("amount", 0) or 0),
            income_receivable=float(d.get("incomeReceivable", 0) or 0), tran_date=str(d.get("tranDate", "")),
        )


@dataclass
class FinanceFile:
    """An uploaded property-portfolio workbook and the rows parsed out of it.

    `namespace` mirrors the frontend contract (ELUserFinanceFile.namespace) -- a stable per-file
    identifier the dashboard uses. Parsed rows are stored so analytics can be recomputed and the
    chat can be grounded without re-reading the original bytes (which are never persisted)."""
    id: str
    tenant: str
    agent_id: str
    file_name: str
    source_name: str
    namespace: str
    size_bytes: int = 0
    row_count: int = 0
    currency: str = DEFAULT_CURRENCY
    expense_rows: list[dict] = field(default_factory=list)
    income_rows: list[dict] = field(default_factory=list)
    uploaded_at: datetime = field(default_factory=_now)

    def expenses(self) -> list[ExpenseRow]:
        return [ExpenseRow.from_dict(r) for r in self.expense_rows]

    def incomes(self) -> list[IncomeRow]:
        return [IncomeRow.from_dict(r) for r in self.income_rows]


@dataclass
class FinanceChatMessage:
    id: str
    tenant: str
    agent_id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime = field(default_factory=_now)


class FinanceFileStore(Protocol):
    async def add(self, file: FinanceFile) -> FinanceFile: ...
    async def get(self, tenant: str, agent_id: str, file_id: str) -> FinanceFile | None: ...
    async def list_for_agent(self, tenant: str, agent_id: str) -> list[FinanceFile]: ...
    async def delete(self, tenant: str, agent_id: str, ids: list[str]) -> list[str]: ...


class FinanceChatStore(Protocol):
    async def add(self, message: FinanceChatMessage) -> FinanceChatMessage: ...
    async def list_for_agent(self, tenant: str, agent_id: str, limit: int | None = None) -> list[FinanceChatMessage]: ...
    async def clear(self, tenant: str, agent_id: str) -> int: ...


@dataclass
class InMemoryFinanceFileStore:
    _by_id: dict[str, FinanceFile] = field(default_factory=dict)

    async def add(self, file: FinanceFile) -> FinanceFile:
        self._by_id[file.id] = file
        return file

    async def get(self, tenant: str, agent_id: str, file_id: str) -> FinanceFile | None:
        f = self._by_id.get(file_id)
        return f if f and f.tenant == tenant and f.agent_id == agent_id else None

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[FinanceFile]:
        items = [f for f in self._by_id.values() if f.tenant == tenant and f.agent_id == agent_id]
        items.sort(key=lambda f: f.uploaded_at, reverse=True)
        return items

    async def delete(self, tenant: str, agent_id: str, ids: list[str]) -> list[str]:
        # Tenant-scoped: only ever removes rows this tenant/agent owns (BOLA-safe) -- an id
        # belonging to another tenant is silently ignored, never deleted.
        deleted: list[str] = []
        for file_id in ids:
            f = self._by_id.get(file_id)
            if f and f.tenant == tenant and f.agent_id == agent_id:
                del self._by_id[file_id]
                deleted.append(file_id)
        return deleted


@dataclass
class InMemoryFinanceChatStore:
    _by_id: dict[str, FinanceChatMessage] = field(default_factory=dict)

    async def add(self, message: FinanceChatMessage) -> FinanceChatMessage:
        self._by_id[message.id] = message
        return message

    async def list_for_agent(self, tenant: str, agent_id: str, limit: int | None = None) -> list[FinanceChatMessage]:
        items = [m for m in self._by_id.values() if m.tenant == tenant and m.agent_id == agent_id]
        items.sort(key=lambda m: m.created_at)
        if limit:
            return items[-limit:]
        return items

    async def clear(self, tenant: str, agent_id: str) -> int:
        to_delete = [mid for mid, m in self._by_id.items() if m.tenant == tenant and m.agent_id == agent_id]
        for mid in to_delete:
            del self._by_id[mid]
        return len(to_delete)
