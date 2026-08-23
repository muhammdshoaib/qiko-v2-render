"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { DataTable, Input, type Column, type SortOrder } from "@qiko/ui";
import type { FinanceUnitExpense } from "@/lib/api";
import { useFinance } from "./finance-context";
import { allExpenses, formatCurrency, formatDateShort } from "./utils";

export type ExpenseListFilter = {
  propertyRef?: string;
  unitRef?: string;
  vendorName?: string;
  category?: string;
};

export function ExpenseList({
  filter,
  showSearch = true,
  hideProperty = false,
  hideUnit = false,
  hideViewUnitAction = false,
  title = "Expenses",
}: {
  filter?: ExpenseListFilter;
  showSearch?: boolean;
  hideProperty?: boolean;
  hideUnit?: boolean;
  /** Suppress the per-row "View unit" action: redundant when the list is already scoped to one unit. */
  hideViewUnitAction?: boolean;
  title?: string;
}) {
  const { agentId, analytics, currency } = useFinance();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<string>("invoiceDate");
  const [order, setOrder] = useState<SortOrder>("desc");

  const base = useMemo(() => allExpenses(analytics, showSearch ? search : ""), [analytics, search, showSearch]);

  const rows = useMemo(() => {
    let list = base;
    if (filter?.propertyRef) list = list.filter((r) => r.propertyRef === filter.propertyRef);
    if (filter?.unitRef) list = list.filter((r) => r.unitRef === filter.unitRef);
    if (filter?.vendorName) list = list.filter((r) => (r.supplierName ?? "").toLowerCase() === filter.vendorName!.toLowerCase());
    if (filter?.category) list = list.filter((r) => (r.heading ?? "").toLowerCase() === filter.category!.toLowerCase());

    return list.sort((a, b) => {
      let av: unknown, bv: unknown;
      if (sort === "property") { av = a.propertyName; bv = b.propertyName; }
      else if (sort === "unit") { av = a.unitDescription || a.unitRef; bv = b.unitDescription || b.unitRef; }
      else { av = (a as Record<string, unknown>)[sort]; bv = (b as Record<string, unknown>)[sort]; }

      if (typeof av === "number" && typeof bv === "number") return order === "asc" ? av - bv : bv - av;
      const as = String(av ?? ""), bs = String(bv ?? "");
      return order === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
  }, [base, filter, sort, order]);

  const columns = useMemo<Column<FinanceUnitExpense>[]>(() => {
    const cols: Column<FinanceUnitExpense>[] = [];
    if (!hideProperty) {
      cols.push({
        id: "property",
        header: "Property",
        rowHeader: true,
        cell: (e) => (
          <button
            type="button"
            onClick={() => router.push(`/studio/${agentId}/finance/property/${encodeURIComponent(e.propertyRef ?? "")}`)}
            className="text-left text-indigo-300 hover:underline"
          >
            {e.propertyName || e.propertyRef}
          </button>
        ),
      });
    }
    if (!hideUnit) {
      cols.push({ id: "unit", header: "Unit", cell: (e) => e.unitDescription || e.unitRef });
    }
    cols.push(
      { id: "heading", header: "Category", cell: (e) => e.heading },
      { id: "expenditureDescription", header: "Description", cell: (e) => e.expenditureDescription },
      { id: "supplierName", header: "Vendor", cell: (e) => e.supplierName },
      { id: "nett", header: "Nett", numeric: true, sortable: true, cell: (e) => formatCurrency(e.nett, currency) },
      { id: "vat", header: "VAT", numeric: true, sortable: true, cell: (e) => formatCurrency(e.vat, currency) },
      { id: "gross", header: "Gross", numeric: true, sortable: true, cell: (e) => formatCurrency(e.gross, currency) },
      { id: "invoiceDate", header: "Date", sortable: true, cell: (e) => formatDateShort(e.invoiceDate) },
      { id: "settled", header: "Settled", cell: (e) => e.settled || "-" },
    );
    return cols;
  }, [agentId, router, hideProperty, hideUnit, currency]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white/88">{title}</h3>
        {showSearch && (
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/45" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search expenses..."
              className="h-9 pl-8 text-xs"
            />
          </div>
        )}
      </div>
      <p className="text-xs text-white/50">{rows.length} expense rows</p>
      <DataTable
        caption={title}
        rows={rows}
        rowKey={(e) => `${e.propertyRef ?? ""}-${e.unitRef ?? ""}-${e.heading ?? ""}-${e.supplierName ?? ""}-${e.gross ?? 0}-${e.invoiceDate ?? ""}`}
        columns={columns}
        sort={sort}
        order={order}
        onSortChange={(s, o) => { setSort(s); setOrder(o); }}
        actions={hideViewUnitAction ? undefined : (e) =>
          e.unitRef ? (
            <button
              type="button"
              onClick={() => router.push(`/studio/${agentId}/finance/property/${encodeURIComponent(e.propertyRef ?? "")}?unit=${encodeURIComponent(e.unitRef ?? "")}`)}
              className="text-xs text-indigo-300 hover:underline"
            >
              View unit
            </button>
          ) : null
        }
      />
    </div>
  );
}
