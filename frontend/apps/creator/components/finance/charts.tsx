"use client";

// Chart building blocks for the Financial Analyst dashboard -- recharts (already a dep), styled to
// match the sales-intelligence cockpit + the reference screenshots (green income bars, small red
// expense bars, purple-gradient donuts, thin horizontal progress bars for vendors/risk).
import { Activity, AlertTriangle, BarChart3, DollarSign, Info, PieChart as PieChartIcon, Tag } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { cn } from "@qiko/ui";
import { useFinance } from "./finance-context";
import {
  EXPENSE_COLOR, INCOME_COLOR, RISK_ASSESSMENT_TOOLTIP,
  formatCompact, formatCurrency, type DonutSlice, type PropertyBar, type RiskRow, type VendorRow,
} from "./utils";

const TOOLTIP_STYLE = { background: "#0f1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12, color: "#e2e8f0" } as const;
const AXIS_TICK = { fill: "#64748b", fontSize: 11 } as const;

function truncate(label: string, max = 22): string {
  const s = String(label ?? "");
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

export function ChartCard({ title, icon, iconColor, action, children }: {
  title: string; icon: React.ReactNode; iconColor?: string; action?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border p-5" style={{ background: "oklch(0.16 0.02 250)" }}>
      <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground/88">
        <span className={cn("shrink-0", iconColor)}>{icon}</span>
        {title}
        {action}
      </h3>
      {children}
    </div>
  );
}

// ── Income vs Expenses grouped bar ───────────────────────────────────────────────────────────────
export function IncomeExpensesChart({ data, onPropertyClick }: { data: PropertyBar[]; onPropertyClick?: (ref: string, name: string) => void }) {
  const { currency } = useFinance();
  const handleBarClick = (_: unknown, index: number) => {
    const p = data[index];
    if (p && onPropertyClick) onPropertyClick(p.propertyRef, p.propertyName);
  };

  return (
    <ChartCard title="Income vs Expenses by Property" icon={<BarChart3 className="h-4 w-4" />} iconColor="text-indigo-400">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis dataKey="name" tick={AXIS_TICK} angle={-35} textAnchor="end" height={60} tickFormatter={(v) => truncate(String(v))} />
          <YAxis tick={AXIS_TICK} tickFormatter={(v) => formatCompact(Number(v), currency)} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v) => formatCurrency(Number(v), currency)} />
          <Bar dataKey="income" name="Income" fill={INCOME_COLOR} radius={[4, 4, 0, 0]} onClick={handleBarClick} />
          <Bar dataKey="expenses" name="Expenses" fill={EXPENSE_COLOR} radius={[4, 4, 0, 0]} onClick={handleBarClick} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Profitability Classification donut ────────────────────────────────────────────────────────────
export function ProfitabilityDonut({ data, onClassClick }: { data: DonutSlice[]; onClassClick?: (cls: string) => void }) {
  return (
    <ChartCard title="Profitability Classification" icon={<PieChartIcon className="h-4 w-4" />} iconColor="text-green-400">
      <div className="flex h-[220px] items-center justify-center">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]}
              cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value" stroke="transparent"
              onClick={(_, index) => { const d = data[index]; if (d && onClassClick) onClassClick(d.key); }}>
              {(data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]).map((entry, i) => (
                <Cell key={i} fill={entry.color} className={onClassClick ? "cursor-pointer" : undefined} />
              ))}
            </Pie>
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={false} formatter={(v, n) => [`${Number(v)} properties`, String(n)]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-3">
        {data.map((d, i) => (
          <button key={i} type="button" disabled={!onClassClick} onClick={() => onClassClick?.(d.key)}
            className="flex items-center gap-1.5 disabled:cursor-default">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: d.color }} />
            <span className="text-[11px] text-white/68">{d.name} ({d.value})</span>
          </button>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Top Vendors by Spend (ranked list with thin progress bars) ─────────────────────────────────────
export function VendorSpendList({ data, onVendorClick }: { data: VendorRow[]; onVendorClick?: (name: string) => void }) {
  const { currency } = useFinance();
  return (
    <ChartCard title="Top Vendors by Spend" icon={<Tag className="h-4 w-4" />} iconColor="text-purple-400">
      <div className="space-y-2.5">
        {data.length === 0 && <p className="text-xs text-slate-400">No vendor spend in this period.</p>}
        {data.map((v, i) => (
          <button key={i} type="button" onClick={() => onVendorClick?.(v.name)}
            className="w-full text-left disabled:cursor-default" disabled={!onVendorClick}>
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="min-w-0 flex-1 break-words text-xs text-white/72">{v.name}</span>
              <span className="shrink-0 text-xs text-slate-500">{formatCurrency(v.spend, currency)} ({v.percent}%)</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, v.percent)}%`, background: v.color, minWidth: 4 }} />
            </div>
          </button>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Expense Categories donut ──────────────────────────────────────────────────────────────────────
export function ExpenseCategoriesDonut({ data, onCategoryClick }: { data: DonutSlice[]; onCategoryClick?: (cat: string) => void }) {
  const { currency } = useFinance();
  return (
    <ChartCard title="Expense Categories" icon={<DollarSign className="h-4 w-4" />} iconColor="text-amber-700">
      <div className="flex h-[220px] items-center justify-center">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]}
              cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={2} dataKey="value" stroke="transparent"
              onClick={(_, index) => { const d = data[index]; if (d && onCategoryClick) onCategoryClick(d.key); }}>
              {(data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]).map((entry, i) => (
                <Cell key={i} fill={entry.color} className={onCategoryClick ? "cursor-pointer" : undefined} />
              ))}
            </Pie>
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={false} formatter={(v, n) => [formatCurrency(Number(v), currency), String(n)]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {data.slice(0, 6).map((d, i) => (
          <button key={i} type="button" disabled={!onCategoryClick} onClick={() => onCategoryClick?.(d.key)}
            className="flex items-center gap-1.5 disabled:cursor-default">
            <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
            <span className="text-[10px] text-slate-500">{d.name}</span>
          </button>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Risk Score by Property (list with tier pill + colored progress bar) ─────────────────────────────
export function RiskScoreList({ data, onPropertyClick }: { data: RiskRow[]; onPropertyClick?: (ref: string, name: string) => void }) {
  return (
    <ChartCard
      title="Risk Score by Property"
      icon={<AlertTriangle className="h-4 w-4" />}
      iconColor="text-red-400"
      action={<span title={RISK_ASSESSMENT_TOOLTIP} className="inline-flex cursor-help text-slate-400 hover:text-indigo-600"><Info className="h-3.5 w-3.5" /></span>}
    >
      <div className="space-y-2">
        {data.length === 0 && <p className="text-xs text-slate-400">No risk data available.</p>}
        {data.map((r, i) => (
          <button key={i} type="button" disabled={!onPropertyClick} onClick={() => onPropertyClick?.(r.propertyRef, r.propertyName)}
            className="w-full text-left disabled:cursor-default">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-white/72">{r.name}</span>
              <div className="flex items-center gap-2">
                <span className="rounded px-1 py-0 text-[9px] font-medium capitalize" style={{ color: r.color, background: `${r.color}22` }}>{r.riskLevel}</span>
                <span className="font-mono text-xs text-slate-500">{r.riskScore}/100</span>
              </div>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, r.riskScore)}%`, background: r.color }} />
            </div>
          </button>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Property Profitability Ranking (green bar chart, red when negative) ─────────────────────────────
export function ProfitabilityRankingChart({ data, onPropertyClick }: { data: PropertyBar[]; onPropertyClick?: (ref: string, name: string) => void }) {
  const { currency } = useFinance();
  const handleBarClick = (_: unknown, index: number) => {
    const p = data[index];
    if (p && onPropertyClick) onPropertyClick(p.propertyRef, p.propertyName);
  };

  return (
    <ChartCard title="Property Profitability Ranking" icon={<Activity className="h-4 w-4" />} iconColor="text-indigo-400">
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis dataKey="name" tick={AXIS_TICK} angle={-35} textAnchor="end" height={60} tickFormatter={(v) => truncate(String(v))} />
          <YAxis tick={AXIS_TICK} tickFormatter={(v) => formatCompact(Number(v), currency)} />
          {/* Bars are colored per-point via <Cell> below, not via a top-level Bar fill, so Recharts
              has no series color to key its default tooltip item text off - force it explicitly
              or it renders black on this dark tooltip background. */}
          <Tooltip contentStyle={TOOLTIP_STYLE} itemStyle={{ color: "#e2e8f0" }} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v) => formatCurrency(Number(v), currency)} />
          <Bar dataKey="profit" name="Net Profit" radius={[4, 4, 0, 0]} onClick={handleBarClick}>
            {data.map((entry, i) => <Cell key={i} fill={entry.profit >= 0 ? INCOME_COLOR : EXPENSE_COLOR} className={onPropertyClick ? "cursor-pointer" : undefined} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
