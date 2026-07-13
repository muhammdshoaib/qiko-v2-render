"use client";

// Chart building blocks for the Financial Analyst dashboard -- recharts (already a dep), styled to
// match the sales-intelligence cockpit + the reference screenshots (green income bars, small red
// expense bars, purple-gradient donuts, thin horizontal progress bars for vendors/risk).
import { Activity, AlertTriangle, BarChart3, DollarSign, Info, PieChart as PieChartIcon, Tag } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { cn } from "@qiko/ui";
import {
  EXPENSE_COLOR, INCOME_COLOR, RISK_ASSESSMENT_TOOLTIP,
  formatCurrency, type DonutSlice, type PropertyBar, type RiskRow, type VendorRow,
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
    <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: "oklch(0.16 0.02 250)" }}>
      <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white/88">
        <span className={cn("shrink-0", iconColor)}>{icon}</span>
        {title}
        {action}
      </h3>
      {children}
    </div>
  );
}

// ── Income vs Expenses grouped bar ───────────────────────────────────────────────────────────────
export function IncomeExpensesChart({ data }: { data: PropertyBar[] }) {
  return (
    <ChartCard title="Income vs Expenses by Property" icon={<BarChart3 className="h-4 w-4" />} iconColor="text-indigo-400">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis dataKey="name" tick={AXIS_TICK} angle={-35} textAnchor="end" height={60} tickFormatter={(v) => truncate(String(v))} />
          <YAxis tick={AXIS_TICK} tickFormatter={(v) => `£${(Number(v) / 1000).toFixed(0)}k`} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v) => formatCurrency(Number(v))} />
          <Bar dataKey="income" name="Income" fill={INCOME_COLOR} radius={[4, 4, 0, 0]} />
          <Bar dataKey="expenses" name="Expenses" fill={EXPENSE_COLOR} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Profitability Classification donut ────────────────────────────────────────────────────────────
export function ProfitabilityDonut({ data }: { data: DonutSlice[] }) {
  return (
    <ChartCard title="Profitability Classification" icon={<PieChartIcon className="h-4 w-4" />} iconColor="text-green-400">
      <div className="flex h-[220px] items-center justify-center">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]}
              cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value" stroke="transparent">
              {(data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]).map((entry, i) => (
                <Cell key={i} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={false} formatter={(v, n) => [`${Number(v)} properties`, String(n)]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-3">
        {data.map((d, i) => (
          <span key={i} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: d.color }} />
            <span className="text-[11px] text-white/68">{d.name} ({d.value})</span>
          </span>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Top Vendors by Spend (ranked list with thin progress bars) ─────────────────────────────────────
export function VendorSpendList({ data }: { data: VendorRow[] }) {
  return (
    <ChartCard title="Top Vendors by Spend" icon={<Tag className="h-4 w-4" />} iconColor="text-purple-400">
      <div className="space-y-2.5">
        {data.length === 0 && <p className="text-xs text-white/45">No vendor spend in this period.</p>}
        {data.map((v, i) => (
          <div key={i} className="w-full text-left">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="min-w-0 flex-1 break-words text-xs text-white/72">{v.name}</span>
              <span className="shrink-0 text-xs text-white/58">{formatCurrency(v.spend)} ({v.percent}%)</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, v.percent)}%`, background: v.color, minWidth: 4 }} />
            </div>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Expense Categories donut ──────────────────────────────────────────────────────────────────────
export function ExpenseCategoriesDonut({ data }: { data: DonutSlice[] }) {
  return (
    <ChartCard title="Expense Categories" icon={<DollarSign className="h-4 w-4" />} iconColor="text-amber-400">
      <div className="flex h-[220px] items-center justify-center">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]}
              cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={2} dataKey="value" stroke="transparent">
              {(data.length ? data : [{ key: "none", name: "No data", value: 1, color: "#334155" }]).map((entry, i) => (
                <Cell key={i} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={false} formatter={(v, n) => [formatCurrency(Number(v)), String(n)]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {data.slice(0, 6).map((d, i) => (
          <span key={i} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
            <span className="text-[10px] text-white/62">{d.name}</span>
          </span>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Risk Score by Property (list with tier pill + colored progress bar) ─────────────────────────────
export function RiskScoreList({ data }: { data: RiskRow[] }) {
  return (
    <ChartCard
      title="Risk Score by Property"
      icon={<AlertTriangle className="h-4 w-4" />}
      iconColor="text-red-400"
      action={<span title={RISK_ASSESSMENT_TOOLTIP} className="inline-flex cursor-help text-white/45 hover:text-indigo-300"><Info className="h-3.5 w-3.5" /></span>}
    >
      <div className="space-y-2">
        {data.length === 0 && <p className="text-xs text-white/45">No risk data available.</p>}
        {data.map((r, i) => (
          <div key={i} className="w-full text-left">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-white/72">{r.name}</span>
              <div className="flex items-center gap-2">
                <span className="rounded px-1 py-0 text-[9px] font-medium capitalize" style={{ color: r.color, background: `${r.color}22` }}>{r.riskLevel}</span>
                <span className="font-mono text-xs text-white/58">{r.riskScore}/100</span>
              </div>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, r.riskScore)}%`, background: r.color }} />
            </div>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}

// ── Property Profitability Ranking (green bar chart, red when negative) ─────────────────────────────
export function ProfitabilityRankingChart({ data }: { data: PropertyBar[] }) {
  return (
    <ChartCard title="Property Profitability Ranking" icon={<Activity className="h-4 w-4" />} iconColor="text-indigo-400">
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis dataKey="name" tick={AXIS_TICK} angle={-35} textAnchor="end" height={60} tickFormatter={(v) => truncate(String(v))} />
          <YAxis tick={AXIS_TICK} tickFormatter={(v) => `£${(Number(v) / 1000).toFixed(0)}k`} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v) => formatCurrency(Number(v))} />
          <Bar dataKey="profit" name="Net Profit" radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => <Cell key={i} fill={entry.profit >= 0 ? INCOME_COLOR : EXPENSE_COLOR} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
