"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { DataTable, type Column, type SortOrder } from "@qiko/ui";
import type { FinanceProperty } from "@/lib/api";
import { useFinance } from "./finance-context";
import { formatCurrency } from "./utils";

export function PropertyList({
  sortBy = "name",
  onSelect,
  actions,
  title = "Properties",
}: {
  sortBy?: "name" | "income" | "profit" | "outstanding";
  onSelect?: (propertyRef: string) => void;
  actions?: (p: FinanceProperty) => React.ReactNode;
  title?: string;
}) {
  const { agentId, analytics, currency } = useFinance();
  const router = useRouter();
  const [sort, setSort] = useState<string>(sortBy);
  const [order, setOrder] = useState<SortOrder>("desc");

  const rows = useMemo(() => {
    const list = [...(analytics?.properties ?? [])];
    return list.sort((a, b) => {
      const av = sort === "name" ? (a.name ?? a.propertyRef) : (a as Record<string, unknown>)[sort];
      const bv = sort === "name" ? (b.name ?? b.propertyRef) : (b as Record<string, unknown>)[sort];
      if (typeof av === "number" && typeof bv === "number") return order === "asc" ? av - bv : bv - av;
      const as = String(av ?? ""), bs = String(bv ?? "");
      return order === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
  }, [analytics, sort, order]);

  const columns: Column<FinanceProperty>[] = useMemo(() => [
    {
      id: "name",
      header: "Property",
      rowHeader: true,
      sortable: true,
      cell: (p) => (
        <button
          type="button"
          onClick={() => onSelect?.(p.propertyRef ?? p.propertyId ?? "")}
          className="text-left text-indigo-300 hover:underline"
        >
          {p.name || p.propertyRef || p.propertyId}
        </button>
      ),
    },
    { id: "income", header: "Income", numeric: true, sortable: true, cell: (p) => formatCurrency(p.income, currency) },
    { id: "expenses", header: "Expenses", numeric: true, sortable: true, cell: (p) => formatCurrency(p.expenses, currency) },
    { id: "netProfit", header: "Net Profit", numeric: true, sortable: true, cell: (p) => formatCurrency(p.netProfit, currency) },
    { id: "marginPercent", header: "Margin", numeric: true, sortable: true, cell: (p) => `${p.marginPercent ?? 0}%` },
    { id: "outstanding", header: "Outstanding", numeric: true, sortable: true, cell: (p) => formatCurrency(p.outstanding, currency) },
    { id: "riskScore", header: "Risk", numeric: true, sortable: true, cell: (p) => `${p.riskScore ?? 0}` },
  ], [onSelect, currency]);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-white/88">{title}</h3>
      <DataTable
        caption={title}
        rows={rows}
        rowKey={(p) => p.propertyRef ?? p.propertyId ?? String(p.name)}
        columns={columns}
        sort={sort}
        order={order}
        onSortChange={(s, o) => { setSort(s); setOrder(o); }}
        actions={(p) =>
          actions ? actions(p) : (
            <button
              type="button"
              onClick={() => router.push(`/studio/${agentId}/finance/property/${encodeURIComponent(p.propertyRef ?? p.propertyId ?? "")}`)}
              className="text-xs text-indigo-300 hover:underline"
            >
              View
            </button>
          )
        }
      />
    </div>
  );
}
