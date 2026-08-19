"use client";

// KPI strip for the Financial Analyst dashboard: covers the full Summary Cards field mapping
// from qiko-fields-tracking.pdf (totalIncome, totalExpenses, netProfit, outstanding, propertyCount).
import { Building2, DollarSign, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import { cn } from "@qiko/ui";
import { EXPENSE_COLOR, INCOME_COLOR, PROFIT_COLOR, RECEIVABLE_COLOR, formatCurrency, type NormalizedSummary } from "./utils";

const CARD_STYLE = { background: "oklch(0.16 0.02 250)" } as const;

export type KpiKey = "income" | "expenses" | "profit" | "properties";

function fmt(n: number | null | undefined) {
  return formatCurrency(n);
}

function Card({ label, value, icon: Icon, color, onClick }: {
  label: string; value: React.ReactNode; icon: React.ElementType; color: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn("flex h-full flex-col rounded-xl border border-white/[0.06] p-4 text-left transition-all duration-200 hover:border-indigo-400/35 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/45",
        !onClick && "cursor-default")}
      style={CARD_STYLE}
      disabled={!onClick}
    >
      <div className="flex min-h-[1.25rem] items-center justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wider text-white/55">{label}</span>
        <Icon className="h-4 w-4 shrink-0" style={{ color }} />
      </div>
      <div className="mt-2 break-words text-lg font-bold leading-tight text-white/90 sm:text-xl">{value}</div>
    </button>
  );
}

export function KpiCards({ summary, propertyCount, onOpenPortfolio, onKpiClick }: {
  summary: NormalizedSummary; propertyCount: number; onOpenPortfolio?: () => void; onKpiClick?: (key: KpiKey) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
      <Card label="Total Income" value={summary.formatted.totalIncome ?? fmt(summary.totalIncome)} icon={TrendingUp} color={INCOME_COLOR} onClick={() => onKpiClick?.("income")} />
      <Card label="Total Expenses" value={summary.formatted.totalExpenses ?? fmt(summary.totalExpenses)} icon={TrendingDown} color={EXPENSE_COLOR} onClick={() => onKpiClick?.("expenses")} />
      <Card label="Net Profit" value={summary.formatted.netProfit ?? fmt(summary.netProfit)} icon={DollarSign} color={PROFIT_COLOR} onClick={() => onKpiClick?.("profit")} />
      <Card label="Outstanding" value={summary.formatted.outstanding ?? fmt(summary.outstanding)} icon={Wallet} color={RECEIVABLE_COLOR} />
      <Card label="Total Properties" value={propertyCount} icon={Building2} color="#22d3ee" onClick={onOpenPortfolio} />
    </div>
  );
}
