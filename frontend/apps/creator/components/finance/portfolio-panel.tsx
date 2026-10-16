"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpDown, Search } from "lucide-react";
import { cn } from "@qiko/ui";
import { useFinance } from "./finance-context";
import { DrilldownFrame } from "./drilldown-frame";
import { activeProperties, formatCurrency } from "./utils";

type SortKey = "propertyName" | "income" | "expenses";

export function PortfolioPanel() {
  const { agentId, analytics, currency } = useFinance();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("propertyName");
  const [dir, setDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const list = activeProperties(analytics).map((p) => ({
      staNo: p.propertyRef || p.propertyId || p.name || "",
      propertyName: p.name || p.propertyRef || p.propertyId || "Property",
      income: Number(p.income ?? 0),
      expenses: Number(p.expenses ?? 0),
    })).filter((row) => {
      if (!term) return true;
      return row.propertyName.toLowerCase().includes(term) || row.staNo.toLowerCase().includes(term);
    });
    list.sort((a, b) => {
      const av = a[sort];
      const bv = b[sort];
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return dir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [analytics, search, sort, dir]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);

  function toggleSort(key: SortKey) {
    if (sort === key) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSort(key); setDir(key === "propertyName" ? "asc" : "desc"); }
    setPage(1);
  }

  return (
    <DrilldownFrame
      onBack={() => router.push(`/studio/${agentId}/finance`)}
      title="Portfolio properties"
      subtitle={<p className="text-sm text-slate-500">Dedicated table view for portfolio records with sort, search, and pagination for large datasets.</p>}
      headerExtra={(
        <div className="relative ml-auto w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search by property name or code..."
            className="h-9 w-full rounded-lg border border-slate-200 bg-muted pl-9 pr-3 text-xs text-slate-800 outline-none placeholder:text-slate-400 focus:border-indigo-400/50"
          />
        </div>
      )}
      footer={rows.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 px-6 py-3 text-xs text-slate-500">
          <span>
            Showing {(safePage - 1) * pageSize + 1}-{Math.min(safePage * pageSize, rows.length)} of {rows.length}
          </span>
          <div className="inline-flex items-center gap-1">
            <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}
              className="rounded border border-slate-200 px-2 py-1 disabled:opacity-40">Prev</button>
            <span className="px-1">Page {safePage} / {totalPages}</span>
            <button type="button" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}
              className="rounded border border-slate-200 px-2 py-1 disabled:opacity-40">Next</button>
          </div>
        </div>
      ) : null}
    >
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">No properties in the current range.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[28rem] border-collapse text-sm">
            <caption className="sr-only">Portfolio properties</caption>
            <thead className="sticky top-0 z-10 bg-[oklch(0.2_0.035_265)]">
              <tr className="border-b border-border text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3">
                  <button type="button" onClick={() => toggleSort("propertyName")} className="inline-flex items-center gap-1">
                    Property name <ArrowUpDown className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                </th>
                <th className="px-4 py-3 text-right">
                  <button type="button" onClick={() => toggleSort("income")} className={cn("ml-auto inline-flex items-center gap-1")}>
                    Total income <ArrowUpDown className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                </th>
                <th className="px-4 py-3 text-right">
                  <button type="button" onClick={() => toggleSort("expenses")} className="ml-auto inline-flex items-center gap-1">
                    Total expenses <ArrowUpDown className="h-3.5 w-3.5 text-slate-400" />
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => (
                <tr
                  key={row.staNo}
                  role="button"
                  tabIndex={0}
                  onClick={() => router.push(`/studio/${agentId}/finance/property/${encodeURIComponent(row.staNo)}?from=portfolio`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      router.push(`/studio/${agentId}/finance/property/${encodeURIComponent(row.staNo)}?from=portfolio`);
                    }
                  }}
                  className="cursor-pointer border-t border-border text-white/88 transition-colors hover:bg-white/[0.07] focus-visible:bg-white/[0.07] focus-visible:outline-none"
                >
                  <td className="max-w-[14rem] px-4 py-3 font-medium leading-snug text-slate-800">{row.propertyName}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-emerald-300/95">{formatCurrency(row.income, currency)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-rose-300/95">{formatCurrency(row.expenses, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </DrilldownFrame>
  );
}
