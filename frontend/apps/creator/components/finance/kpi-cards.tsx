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

function pct(n: number | null | undefined) {
  return `${(Number(n ?? 0)).toFixed(1)}%`;
}

function Card({ label, value, icon: Icon, color, onClick, children }: {
  label: string; value: React.ReactNode; icon: React.ElementType; color: string;
  onClick?: () => void; children?: React.ReactNode;
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
      {children && <div className="mt-2 space-y-0.5 text-[10px] leading-snug text-white/48">{children}</div>}
    </button>
  );
}

export function KpiCards({ summary, propertyCount, onOpenPortfolio, onKpiClick }: {
  summary: NormalizedSummary; propertyCount: number; onOpenPortfolio?: () => void; onKpiClick?: (key: KpiKey) => void;
}) {
  const d = summary.details;

  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
      <Card label="Total Income" value={summary.formatted.totalIncome ?? fmt(summary.totalIncome)} icon={TrendingUp} color={INCOME_COLOR} onClick={() => onKpiClick?.("income")}>
        {d?.totalIncomeTopProperty && <div>Top: {d.totalIncomeTopProperty} ({fmt(d.totalIncomeTopPropertyIncome)})</div>}
        {d?.totalIncomeAveragePerProperty !== undefined && d.totalIncomeAveragePerProperty > 0 && <div>Avg / property: {fmt(d.totalIncomeAveragePerProperty)}</div>}
        {d?.totalIncomeUnitCount !== undefined && d.totalIncomeUnitCount > 0 && <div>Units: {d.totalIncomeUnitCount}</div>}
      </Card>

      <Card label="Total Expenses" value={summary.formatted.totalExpenses ?? fmt(summary.totalExpenses)} icon={TrendingDown} color={EXPENSE_COLOR} onClick={() => onKpiClick?.("expenses")}>
        {d?.totalExpensesTopVendor && <div>Top vendor: {d.totalExpensesTopVendor} ({fmt(d.totalExpensesTopVendorAmount)})</div>}
        {d?.totalExpensesTopCategory && <div>Top category: {d.totalExpensesTopCategory} ({fmt(d.totalExpensesTopCategoryAmount)})</div>}
        {d?.totalExpensesInvoiceCount !== undefined && d.totalExpensesInvoiceCount > 0 && <div>Invoices: {d.totalExpensesInvoiceCount}</div>}
        {d?.totalExpensesAveragePerProperty !== undefined && d.totalExpensesAveragePerProperty > 0 && <div>Avg / property: {fmt(d.totalExpensesAveragePerProperty)}</div>}
      </Card>

      <Card label="Net Profit" value={summary.formatted.netProfit ?? fmt(summary.netProfit)} icon={DollarSign} color={PROFIT_COLOR} onClick={() => onKpiClick?.("profit")}>
        {d?.netProfitMarginPercent !== undefined && <div>Margin: {pct(d.netProfitMarginPercent)}</div>}
        {d?.netProfitAverageMargin !== undefined && <div>Avg margin: {pct(d.netProfitAverageMargin)}</div>}
        {d?.netProfitTopProperty && <div>Top: {d.netProfitTopProperty} ({fmt(d.netProfitTopPropertyProfit)})</div>}
        {d?.netProfitLowestPerformanceProperty && <div>Worst: {d.netProfitLowestPerformanceProperty} ({fmt(d.netProfitLowestPerformancePropertyProfit)})</div>}
        {d?.netProfitCostToIncomeRatio !== undefined && <div>CTI: {pct(d.netProfitCostToIncomeRatio)}</div>}
      </Card>

      <Card label="Outstanding" value={summary.formatted.outstanding ?? fmt(summary.outstanding)} icon={Wallet} color={RECEIVABLE_COLOR}>
        {d?.outstandingPropertyCount !== undefined && d.outstandingPropertyCount > 0 && <div>Properties with arrears: {d.outstandingPropertyCount}</div>}
        {(d?.outstandingPositiveTotal !== undefined || d?.outstandingNegativeTotal !== undefined) && (d?.outstandingPositiveTotal || d?.outstandingNegativeTotal) && (
          <div>Positive / negative: {fmt(d.outstandingPositiveTotal)} / {fmt(d.outstandingNegativeTotal)}</div>
        )}
        {d?.outstandingTopProperty && <div>Top debtor: {d.outstandingTopProperty} ({fmt(d.outstandingTopPropertyOutstanding)})</div>}
        {d?.outstandingAsPercentOfIncome !== undefined && <div>As % of income: {pct(d.outstandingAsPercentOfIncome)}</div>}
      </Card>

      <Card label="Total Properties" value={propertyCount} icon={Building2} color="#22d3ee" onClick={onOpenPortfolio}>
        {(d?.highPerforming !== undefined || d?.averagePerforming !== undefined || d?.underPerforming !== undefined) && (
          <div>High / Avg / Under: {d?.highPerforming ?? 0} / {d?.averagePerforming ?? 0} / {d?.underPerforming ?? 0}</div>
        )}
        {(d?.highRisk !== undefined || d?.mediumRisk !== undefined || d?.lowRisk !== undefined) && (
          <div>High / Med / Low risk: {d?.highRisk ?? 0} / {d?.mediumRisk ?? 0} / {d?.lowRisk ?? 0}</div>
        )}
        {d?.totalUnits !== undefined && d?.totalInvoices !== undefined && <div>Units / Invoices: {d.totalUnits} / {d.totalInvoices}</div>}
        {(d?.averageIncomePerProperty !== undefined || d?.averageExpensePerProperty !== undefined) && (
          <div>Avg income / expense: {fmt(d?.averageIncomePerProperty)} / {fmt(d?.averageExpensePerProperty)}</div>
        )}
        {d?.topProperty && d?.worstProperty && <div>Top / Worst: {d.topProperty} / {d.worstProperty}</div>}
      </Card>
    </div>
  );
}
