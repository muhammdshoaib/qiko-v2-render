"use client";

import { Building2, DollarSign, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@qiko/ui";
import { EXPENSE_COLOR, INCOME_COLOR, PROFIT_COLOR, formatCurrency, type NormalizedSummary } from "./utils";
import { useFinance } from "./finance-context";

const CARD_STYLE = { background: "oklch(0.16 0.02 250)" } as const;

export type KpiKey = "income" | "expenses" | "profit" | "properties";

function Card({ label, value, icon: Icon, color, onClick, children }: {
  label: string; value: React.ReactNode; icon: React.ElementType; color: string;
  onClick?: () => void; children?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex h-full min-h-0 flex-col rounded-xl border border-border p-4 text-left transition-all duration-200 hover:border-indigo-400/35 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/45",
        !onClick && "cursor-default",
      )}
      style={CARD_STYLE}
      disabled={!onClick}
    >
      <div className="flex min-h-[1.25rem] shrink-0 items-center justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">{label}</span>
        <Icon className="h-4 w-4 shrink-0" style={{ color }} />
      </div>
      <div className="mt-2 min-h-[1.75rem] shrink-0 break-words text-lg font-bold leading-tight text-slate-800 sm:text-xl">{value}</div>
      {children}
    </button>
  );
}

export function KpiCards({ summary, propertyCount, onOpenPortfolio, onKpiClick }: {
  summary: NormalizedSummary; propertyCount: number; onOpenPortfolio?: () => void; onKpiClick?: (key: KpiKey) => void;
}) {
  const { currency } = useFinance();
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-4">
      <Card label="Total Income" value={formatCurrency(summary.totalIncome, currency)} icon={TrendingUp} color={INCOME_COLOR} onClick={() => onKpiClick?.("income")} />
      <Card label="Total Expenses" value={formatCurrency(summary.totalExpenses, currency)} icon={TrendingDown} color={EXPENSE_COLOR} onClick={() => onKpiClick?.("expenses")} />
      <Card label="Net Profit" value={formatCurrency(summary.netProfit, currency)} icon={DollarSign} color={PROFIT_COLOR} onClick={() => onKpiClick?.("profit")} />
      <Card label="Total Properties" value={propertyCount} icon={Building2} color="#22d3ee" onClick={onOpenPortfolio}>
        <div className="mt-1 min-h-[2.75rem] text-[10px] leading-snug text-foreground/48">Open portfolio table</div>
      </Card>
    </div>
  );
}
