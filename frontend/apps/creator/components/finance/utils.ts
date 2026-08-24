// Analytics-derivation + formatting helpers for the Financial Analyst dashboard. Ported faithfully
// from the original qiko-frontend financial dashboard (userDashboard.tsx + userAnalyticsToDashboard.ts)
// but re-typed against lib/api.ts's FinanceAnalytics contract. All derivation is defensive: the
// backend `charts`/`insights`/`trends` shapes may firm up later (see TODO(finance-backend) in api.ts),
// so the dashboard derives everything it can from `properties[]` when a chart block is absent.
import type {
  FinanceAnalytics, FinanceProperty, FinanceSummary, FinanceTrends,
  FinanceUnitExpense, FinanceUnitLedger, FinanceMonthlyTrend, FinanceFile,
} from "@/lib/api";

// ── Colors (match the reference: green=income/positive, red=expenses/negative, amber/orange=risk,
// indigo/violet accents + purple-gradient donut segments) ─────────────────────────────────────────
export const INCOME_COLOR = "#22c55e";
export const EXPENSE_COLOR = "#ef4444";
export const PROFIT_COLOR = "#6366f1";
export const RECEIVABLE_COLOR = "#f59e0b";

/** Purple-gradient donut palette used for vendors + expense categories. */
export const CHART_COLORS = [
  "#6366f1", "#8b5cf6", "#a78bfa", "#c084fc",
  "#e879f9", "#f472b6", "#fb7185", "#f97316",
  "#eab308", "#22c55e", "#14b8a6", "#06b6d4",
];

export const CLASSIFICATION_COLORS: Record<string, string> = {
  "high-performing": "#22c55e",
  profitable: "#6366f1",
  "low-margin": "#f59e0b",
  "loss-making": "#ef4444",
};

export const RISK_ASSESSMENT_TOOLTIP =
  "Risk assessment evaluates financial and operational risk using cost-to-income ratio, outstanding balance, expense patterns, and overall profitability.";

/** Hex for a risk tier -- must match the "Risk Score by Property" bar/badge colors. */
export function riskLevelHex(level: string | undefined): string {
  const l = String(level || "low").toLowerCase();
  if (l === "critical") return "#ef4444";
  if (l === "high") return "#f97316";
  if (l === "medium") return "#f59e0b";
  return "#22c55e";
}

// ── Formatting ────────────────────────────────────────────────────────────────────────────────
export function formatCurrency(value: number | null | undefined, currency = "GBP"): string {
  if (value == null || !Number.isFinite(Number(value))) return "-";
  const n = Number(value);
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: 2 }).format(n);
  } catch {
    return `£${n.toLocaleString("en-GB")}`;
  }
}

export function formatCompact(value: number | null | undefined, currency = "GBP"): string {
  const n = Number(value ?? 0);
  if (!n) return formatCurrency(0, currency);
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(n);
  } catch {
    return formatCurrency(n, currency);
  }
}

export function formatPercent(fraction: number | null | undefined): string {
  return `${(Number(fraction ?? 0) * 100).toFixed(1)}%`;
}

export function formatHistoryTime(timestamp: number): string {
  const ms = timestamp > 1e12 ? timestamp : timestamp * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function readableLabel(key: string): string {
  return key
    .replace(/([A-Z])/g, " $1")
    .replace(/\./g, " ")
    .trim()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function isPercentKey(key: string): boolean {
  return /(Percent|Ratio|AsPercent|Margin)/.test(key);
}

function isCountKey(key: string): boolean {
  return /(Count|Performing|Risk|Units|Invoices|Score)$/.test(key);
}

function formatField(key: string, value: unknown, currency = "GBP"): string {
  if (value == null) return "-";
  if (typeof value === "string") return value.trim() || "-";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "-";
    if (isPercentKey(key)) return `${value}%`;
    if (isCountKey(key)) return String(value);
    return formatCurrency(value, currency);
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return "-";
}

// ── Summary normalization (summary is the typed FinanceSummaryOut object from the backend) ───────
export type NormalizedSummary = {
  totalIncome: number; totalExpenses: number; netProfit: number; outstanding: number;
  propertyCount: number; vendorCount: number;
};

export function normalizeFinanceSummary(summary: FinanceSummary | undefined): NormalizedSummary {
  const totalIncome = Number(summary?.totalIncome ?? 0);
  const totalExpenses = Number(summary?.totalExpenses ?? 0);
  return {
    totalIncome,
    totalExpenses,
    netProfit: Number(summary?.netProfit ?? totalIncome - totalExpenses),
    outstanding: Number(summary?.outstanding ?? 0),
    propertyCount: Number(summary?.propertyCount ?? 0),
    vendorCount: Number(summary?.vendorCount ?? 0),
  };
}

export type KpiMetricKey = "totalIncome" | "totalExpenses" | "netProfit";

const KPI_TITLES: Record<KpiMetricKey, string> = {
  totalIncome: "Total Income",
  totalExpenses: "Total Expenses",
  netProfit: "Net Profit",
};

/** Extra fields shown on the KPI click screen (same filtering as V1 userDashboard). */
export function kpiMetricDrilldown(summary: FinanceSummary | undefined, key: KpiMetricKey, currency = "GBP"): {
  title: string;
  formatted: string;
  details: Array<[string, string]>;
} {
  const source = summary ?? {} as Record<string, unknown>;
  const total = Number((source as Record<string, unknown>)[key] ?? 0);

  const details: Array<[string, string]> = [];
  if (key === "totalExpenses" && source.expenseBreakdown && typeof source.expenseBreakdown === "object") {
    for (const [subKey, subValue] of Object.entries(source.expenseBreakdown)) {
      details.push([readableLabel(`expenseBreakdown.${subKey}`), formatField(subKey, subValue, currency)]);
    }
  }

  for (const [k, value] of Object.entries(source)) {
    if (k === key) continue;
    if (k === "expenseBreakdown") continue;
    if (!k.startsWith(key)) continue;
    details.push([readableLabel(k), formatField(k, value, currency)]);
  }

  return {
    title: KPI_TITLES[key],
    formatted: formatCurrency(total, currency),
    details,
  };
}

// ── Property display filter (hide all-zero rows, like financialDisplayFilters.isActiveElApiProperty) ─
const EPS = 1e-6;
export function isActiveProperty(p: FinanceProperty): boolean {
  return (
    Math.abs(Number(p.income ?? 0)) > EPS ||
    Math.abs(Number(p.expenses ?? 0)) > EPS ||
    Math.abs(Number(p.outstanding ?? 0)) > EPS ||
    Math.abs(Number(p.netProfit ?? 0)) > EPS
  );
}

export function activeProperties(analytics: FinanceAnalytics | undefined): FinanceProperty[] {
  return (analytics?.properties ?? []).filter(isActiveProperty);
}

function mapClassification(raw: string | undefined): keyof typeof CLASSIFICATION_COLORS {
  const n = (raw || "").toLowerCase().replace(/_/g, "-");
  if (n.includes("high") && n.includes("perform")) return "high-performing";
  if (n.includes("loss")) return "loss-making";
  if (n.includes("low") && n.includes("margin")) return "low-margin";
  return "profitable";
}

// ── Derived chart datasets ────────────────────────────────────────────────────────────────────
export type PropertyBar = {
  name: string; fullName: string; propertyName: string; propertyRef: string; staNo: string;
  income: number; expenses: number; profit: number; margin: number;
};

/** Income / expenses / profit per property, top 10 by profit. Prefers charts.incomeVsExpensesByProperty
 * when present, otherwise derives from properties[]. */
export function propertyBars(analytics: FinanceAnalytics | undefined): PropertyBar[] {
  const chart = analytics?.charts?.incomeVsExpensesByProperty;
  if (Array.isArray(chart) && chart.length > 0) {
    return chart.map((p) => {
      const income = Number(p.income ?? 0);
      const expenses = Number(p.expenses ?? 0);
      const profit = Number(p.netProfit ?? income - expenses);
      const margin = income > 0 ? (profit / income) * 100 : 0;
      const name = String(p.propertyName ?? "-");
      return { name, fullName: name, propertyName: name, propertyRef: String(p.propertyRef ?? name), staNo: String(p.propertyId ?? name), income, expenses, profit, margin };
    }).sort((a, b) => b.profit - a.profit).slice(0, 10);
  }

  const props = activeProperties(analytics);
  const rows: PropertyBar[] = props.map((p) => {
    const income = Number(p.income ?? 0);
    const expenses = Number(p.expenses ?? 0);
    const profit = Number(p.netProfit ?? income - expenses);
    const margin = income > 0 ? (profit / income) * 100 : Number(p.marginPercent ?? 0);
    const name = String(p.name ?? p.propertyId ?? "-");
    return { name, fullName: name, propertyName: name, propertyRef: String(p.propertyRef ?? name), staNo: String(p.propertyId ?? name), income, expenses, profit, margin };
  });
  return rows.sort((a, b) => b.profit - a.profit).slice(0, 10);
}

export type DonutSlice = { key: string; name: string; value: number; color: string };

export function classificationDonut(analytics: FinanceAnalytics | undefined): DonutSlice[] {
  // Classify every property the backend counted in Total Properties (summary.propertyCount),
  // not just the ones with non-zero activity this period - mapClassification always returns a
  // safe default, so there's no reason to silently drop a property here (EL-1005: doing so made
  // the donut's slices undercount vs the KPI card whenever a property had a zero-value period).
  const counts: Record<string, number> = {};
  for (const p of analytics?.properties ?? []) {
    const cls = mapClassification(p.profitabilityClass);
    counts[cls] = (counts[cls] || 0) + 1;
  }
  return Object.entries(counts).map(([key, value]) => ({
    key,
    name: key.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    value,
    color: CLASSIFICATION_COLORS[key] || "#888",
  }));
}

export function expenseCategoryDonut(analytics: FinanceAnalytics | undefined): DonutSlice[] {
  const map = new Map<string, number>();
  for (const p of activeProperties(analytics)) {
    for (const c of p.expenseCategories ?? []) {
      map.set(c.category, (map.get(c.category) || 0) + Number(c.amount ?? 0));
    }
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, value], i) => ({
      key: name,
      name: name.length > 20 ? `${name.slice(0, 20)}…` : name,
      value,
      color: CHART_COLORS[i % CHART_COLORS.length],
    }));
}

export type VendorRow = { name: string; fullName: string; spend: number; percent: number; color: string };

/** Top vendors by spend. Prefers charts.topVendorsBySpend, otherwise aggregates property topVendors. */
export function vendorRows(analytics: FinanceAnalytics | undefined): VendorRow[] {
  const totalExpenses = normalizeFinanceSummary(analytics?.summary).totalExpenses;
  const fromCharts = analytics?.charts?.topVendorsBySpend;
  let rows: { vendorName: string; amount: number; sharePercent?: number }[];
  if (Array.isArray(fromCharts) && fromCharts.length > 0) {
    rows = fromCharts;
  } else {
    const map = new Map<string, number>();
    for (const p of activeProperties(analytics)) {
      for (const v of p.topVendors ?? []) {
        map.set(v.vendorName, (map.get(v.vendorName) || 0) + Number(v.amount ?? 0));
      }
    }
    rows = Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([vendorName, amount]) => ({ vendorName, amount }));
  }
  return rows.slice(0, 8).map((v, i) => {
    const spend = Number(v.amount ?? 0);
    const percent = v.sharePercent != null
      ? Number(v.sharePercent)
      : totalExpenses > 0 ? (spend / totalExpenses) * 100 : 0;
    return { name: v.vendorName, fullName: v.vendorName, spend, percent, color: CHART_COLORS[i % CHART_COLORS.length] };
  });
}

export type RiskRow = { name: string; fullName: string; propertyRef: string; propertyName: string; staNo: string; riskScore: number; riskLevel: string; color: string };

export function riskRows(analytics: FinanceAnalytics | undefined): RiskRow[] {
  return activeProperties(analytics)
    .map((p) => {
      const name = String(p.name ?? p.propertyRef ?? p.propertyId ?? "-");
      const level = String(p.riskLevel ?? "low").toLowerCase();
      return {
        name, fullName: name, propertyRef: String(p.propertyRef ?? name), propertyName: name,
        staNo: String(p.propertyId ?? name),
        riskScore: Math.round(Number(p.riskScore ?? 0)),
        riskLevel: level, color: riskLevelHex(level),
      };
    })
    .sort((a, b) => b.riskScore - a.riskScore)
    .slice(0, 10);
}

// ── Trends / insight rail ───────────────────────────────────────────────────────────────────────
export type TrendInsight = { title: string; text: string };
export type TrendStyle = { accent: string; border: string; badge: string; iconKey: "building" | "alert" | "tag" };
export type TrendSection = { title: string; insights: TrendInsight[] } & TrendStyle;

const TREND_STYLES: TrendStyle[] = [
  { accent: "bg-emerald-400", border: "border-emerald-400/25", badge: "text-emerald-300 border-emerald-400/30 bg-emerald-500/10", iconKey: "building" },
  { accent: "bg-amber-400", border: "border-amber-400/25", badge: "text-amber-300 border-amber-400/30 bg-amber-500/10", iconKey: "alert" },
  { accent: "bg-violet-400", border: "border-violet-400/25", badge: "text-violet-300 border-violet-400/30 bg-violet-500/10", iconKey: "tag" },
];

function trendStyleFor(title: string, index: number): TrendStyle {
  const t = title.toLowerCase();
  if (t.includes("arrear") || t.includes("collection") || t.includes("risk")) return TREND_STYLES[1];
  if (t.includes("vendor") || t.includes("supplier") || t.includes("spend") || t.includes("expense")) return TREND_STYLES[2];
  return TREND_STYLES[index % TREND_STYLES.length];
}

function humanize(key: string): string {
  return key.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function parseTrendInsight(raw: unknown): TrendInsight | null {
  if (!raw) return null;
  if (typeof raw === "string") return raw.trim() ? { title: "", text: raw.trim() } : null;
  if (typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const text = String(o.text ?? o.insightText ?? o.insight ?? o.description ?? "").trim();
  if (!text) return null;
  return { title: String(o.title ?? o.label ?? "").trim(), text };
}

function parseTrendSection(raw: unknown, index: number, fallbackTitle?: string): TrendSection | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const title = String(o.section ?? o.title ?? fallbackTitle ?? "").trim();
  const rawInsights = Array.isArray(o.insights) ? o.insights : [];
  const insights = rawInsights.map(parseTrendInsight).filter(Boolean) as TrendInsight[];
  if (!title || insights.length === 0) return null;
  return { title, insights, ...trendStyleFor(title, index) };
}

/** Normalize the backend `trends` payload into rail sections. Falls back to a helpful default set
 * so the rail is never empty when data exists (mirrors DEFAULT_TRENDS_SECTIONS in the original). */
export function trendSections(payload: FinanceTrends | undefined): TrendSection[] {
  const sections: TrendSection[] = [];
  const collect = (arr: unknown[]) => {
    arr.forEach((item, i) => {
      const s = parseTrendSection(item, i);
      if (s) sections.push(s);
    });
  };

  if (Array.isArray(payload)) {
    collect(payload);
  } else if (payload && typeof payload === "object") {
    const nested = (payload as { trends?: unknown }).trends;
    if (Array.isArray(nested)) {
      collect(nested);
    } else {
      const direct = parseTrendSection(payload, 0);
      if (direct) {
        sections.push(direct);
      } else {
        Object.entries(payload as Record<string, unknown>).forEach(([key, value], i) => {
          const s = parseTrendSection(value, i, humanize(key));
          if (s) sections.push(s);
        });
      }
    }
  }

  return sections;
}

// ── File month options + date helpers ------------------------------------------------------------
export function monthOptionsFromFiles(files?: FinanceFile[]): { label: string; value: string }[] {
  const opts: { label: string; value: string }[] = [{ label: "All time", value: "all" }];
  const seen = new Set<string>();
  if (!files) return opts;
  for (const file of files) {
    if (!file?.uploadedAt) continue;
    const d = new Date(file.uploadedAt);
    if (Number.isNaN(d.getTime())) continue;
    const month = d.toLocaleString("en-GB", { month: "short", year: "numeric" });
    const value = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
    if (!seen.has(value)) {
      seen.add(value);
      opts.push({ label: month, value });
    }
  }
  return opts;
}

export function formatDateShort(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
}

export function allExpenses(analytics: FinanceAnalytics | undefined, search = ""): FinanceUnitExpense[] {
  const q = search.trim().toLowerCase();
  const list: FinanceUnitExpense[] = [];
  for (const p of activeProperties(analytics)) {
    for (const u of p.unitLedger ?? []) {
      for (const e of u.expenses ?? []) {
        const enriched: FinanceUnitExpense = {
          ...e,
          propertyRef: e.propertyRef ?? p.propertyRef ?? p.propertyId,
          propertyName: e.propertyName ?? p.name ?? e.propertyRef,
          unitRef: e.unitRef ?? u.unitRef,
          unitDescription: e.unitDescription ?? u.unitDescription,
        };
        if (!q || [e.heading, e.expenditureDescription, e.supplierName, e.propertyName, e.unitDescription].some((s) => String(s ?? "").toLowerCase().includes(q))) {
          list.push(enriched);
        }
      }
    }
  }
  return list;
}
