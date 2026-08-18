"use client";

// KPI strip for the Financial Analyst dashboard: Total Income, Total Expenses, Net Profit, and a
// Total Properties tile that opens the portfolio table (matches el-finance-dashboard.png).
import { Building2, DollarSign, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@qiko/ui";
import { EXPENSE_COLOR, INCOME_COLOR, PROFIT_COLOR, formatCurrency, type NormalizedSummary } from "./utils";

const CARD_STYLE = { background: "oklch(0.16 0.02 250)" } as const;

type KpiKey = "income" | "expenses" | "profit" | "properties";

export function KpiCards({ summary, propertyCount, onOpenPortfolio, onKpiClick }: {
  summary: NormalizedSummary; propertyCount: number; onOpenPortfolio?: () => void; onKpiClick?: (key: KpiKey) => void;
}) {
  const cards = [
    { key: "income" as KpiKey, label: "Total Income", value: summary.formatted.totalIncome ?? formatCurrency(summary.totalIncome), icon: TrendingUp, color: INCOME_COLOR },
    { key: "expenses" as KpiKey, label: "Total Expenses", value: summary.formatted.totalExpenses ?? formatCurrency(summary.totalExpenses), icon: TrendingDown, color: EXPENSE_COLOR },
    { key: "profit" as KpiKey, label: "Net Profit", value: summary.formatted.netProfit ?? formatCurrency(summary.netProfit), icon: DollarSign, color: PROFIT_COLOR },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-4">
      {cards.map((c) => (
        <button
          key={c.label}
          type="button"
          onClick={() => onKpiClick?.(c.key)}
          className={cn("flex h-full flex-col rounded-xl border border-white/[0.06] p-4 text-left transition-all duration-200 hover:border-indigo-400/35 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/45",
            !onKpiClick && "cursor-default")}
          style={CARD_STYLE}
          disabled={!onKpiClick}
        >
          <div className="flex min-h-[1.25rem] items-center justify-between gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wider text-white/55">{c.label}</span>
            <c.icon className="h-4 w-4 shrink-0" style={{ color: c.color }} />
          </div>
          <div className="mt-2 break-words text-lg font-bold leading-tight text-white/90 sm:text-xl">{c.value}</div>
        </button>
      ))}
      <button
        type="button"
        onClick={onOpenPortfolio}
        className="flex h-full flex-col rounded-xl border border-white/[0.06] p-4 text-left transition-all duration-200 hover:border-indigo-400/35 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/45"
        style={CARD_STYLE}
      >
        <div className="flex min-h-[1.25rem] items-center justify-between gap-2">
          <span className="text-[11px] font-medium uppercase tracking-wider text-white/55">Total Properties</span>
          <Building2 className="h-4 w-4 shrink-0 text-cyan-400" />
        </div>
        <div className="mt-2 text-lg font-bold leading-tight tabular-nums text-white/90 sm:text-xl">{propertyCount}</div>
        <div className="mt-1 text-[10px] leading-snug text-white/48">Open portfolio table</div>
      </button>
    </div>
  );
}
