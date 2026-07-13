"use client";

// Financial Analyst worker dashboard -- analytics over an uploaded property-portfolio workbook.
// Faithful re-skin of the original qiko-frontend financial dashboard (pages/userDashboard.tsx):
// a top toggle (Intelligence / Chat / History), a worker info bar (Search + date filter), a KPI
// strip, the full chart set, and a right-hand TRENDS insight rail -- wired to the new qiko-core
// `/finance/{agentId}/...` API (see lib/api.ts). Empty until a workbook is uploaded.
import { useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3, Building2, Calendar, ChevronDown, Database, History, MessageSquare, Search, Upload,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { getFinanceAnalytics, listAgents, listFinanceFiles, type FinanceAnalytics } from "@/lib/api";
import { KpiCards } from "@/components/finance/kpi-cards";
import { InsightRail } from "@/components/finance/insight-rail";
import { FinanceChatPanel } from "@/components/finance/chat-panel";
import { FinanceHistoryPanel } from "@/components/finance/history-panel";
import { FinanceFileManager, FinanceFileManagerDialog } from "@/components/finance/file-manager";
import {
  ExpenseCategoriesDonut, IncomeExpensesChart, ProfitabilityDonut, ProfitabilityRankingChart,
  RiskScoreList, VendorSpendList,
} from "@/components/finance/charts";
import {
  classificationDonut, expenseCategoryDonut, normalizeFinanceSummary, propertyBars, riskRows,
  trendSections, vendorRows,
} from "@/components/finance/utils";

type Tab = "feed" | "chat" | "history";
const BG = "oklch(0.13 0.025 250)";

export default function FinanceDashboardPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const [tab, setTab] = useState<Tab>("feed");
  const [month, setMonth] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [dateOpen, setDateOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);

  const analyticsQ = useQuery({
    queryKey: ["finance-analytics", agentId, month],
    queryFn: () => getFinanceAnalytics(agentId, month !== "all" ? { month } : {}),
    retry: false,
  });
  const filesQ = useQuery({ queryKey: ["finance-files", agentId], queryFn: () => listFinanceFiles(agentId), retry: false });

  const analytics = analyticsQ.data;
  const hasData = useMemo(() => {
    const props = analytics?.properties?.length ?? 0;
    const rows = Number(analytics?.totalRows ?? 0);
    const files = filesQ.data?.totalFiles ?? 0;
    return props > 0 || (rows > 0 && (analytics?.totalFiles ?? files) > 0);
  }, [analytics, filesQ.data]);

  // Search filters the property-centric visuals (charts/lists); KPI totals stay portfolio-wide.
  const filteredAnalytics = useMemo<FinanceAnalytics | undefined>(() => {
    if (!analytics) return analytics;
    const term = search.trim().toLowerCase();
    if (!term) return analytics;
    return {
      ...analytics,
      properties: (analytics.properties ?? []).filter((p) => String(p.name ?? p.propertyId ?? "").toLowerCase().includes(term)),
    };
  }, [analytics, search]);

  const summary = useMemo(() => normalizeFinanceSummary(analytics?.summary), [analytics]);
  const propertyCount = summary.propertyCount || (analytics?.properties?.filter((p) => (p.income ?? 0) || (p.expenses ?? 0)).length ?? 0);

  const bars = useMemo(() => propertyBars(filteredAnalytics), [filteredAnalytics]);
  const classification = useMemo(() => classificationDonut(filteredAnalytics), [filteredAnalytics]);
  const vendors = useMemo(() => vendorRows(filteredAnalytics), [filteredAnalytics]);
  const expenseCats = useMemo(() => expenseCategoryDonut(filteredAnalytics), [filteredAnalytics]);
  const risks = useMemo(() => riskRows(filteredAnalytics), [filteredAnalytics]);
  const sections = useMemo(() => trendSections(analytics?.trends), [analytics]);

  const monthOptions = useMemo(() => monthOptionsFromFiles(analytics, filesQ.data?.files), [analytics, filesQ.data]);
  const periodLabel = analytics?.dateRange?.label
    ?? (month !== "all" ? monthOptions.find((o) => o.value === month)?.label ?? month : "All");

  const workerName = worker?.name ?? "Financial Analyst";

  return (
    <AppShell title="Studio">
      <div className="flex h-[100dvh] flex-col overflow-hidden" style={{ background: BG }}>
        {/* ── Header: top-right Intelligence / Chat / History toggle ─────────────────── */}
        <header className="flex items-center justify-end border-b border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-1 rounded-full bg-white/[0.06] p-0.5">
            {([
              { key: "feed", label: "Intelligence", icon: BarChart3 },
              { key: "chat", label: "Chat", icon: MessageSquare },
              { key: "history", label: "History", icon: History },
            ] as const).map((t) => (
              <button key={t.key} type="button" onClick={() => setTab(t.key)}
                className={cn("flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all",
                  tab === t.key ? "bg-white/[0.12] text-white" : "text-white/50 hover:text-white/75")}>
                <t.icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            ))}
          </div>
        </header>

        {/* ── Worker info bar (hidden on Chat, like the reference) ───────────────────── */}
        {tab !== "chat" && (
          <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.04] px-4 py-2.5 sm:gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-600">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-white/90">{workerName}</span>
                <span className="rounded-full border border-indigo-500/30 px-1.5 py-0 text-[10px] uppercase tracking-wider text-indigo-400">Template</span>
              </div>
              <p className="text-xs text-white/50">{propertyCount} properties · {summary.vendorCount} vendors</p>
            </div>

            {tab === "feed" && hasData && (
              <div className="flex w-full items-center gap-2 sm:ml-auto sm:w-auto">
                <div className="relative w-full sm:w-[min(26rem,42vw)]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/45" />
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search"
                    className="h-9 w-full rounded-lg border border-white/[0.08] bg-white/[0.04] pl-8 pr-3 text-xs text-white/85 outline-none placeholder:text-white/45 focus:border-indigo-400/45" />
                </div>

                <div className="relative">
                  <button type="button" onClick={() => setDateOpen((v) => !v)}
                    className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs transition-all hover:bg-white/[0.06]">
                    <Calendar className="h-3.5 w-3.5 text-indigo-400" />
                    <span className="font-medium text-white/80">{periodLabel}</span>
                    <ChevronDown className={cn("h-3 w-3 text-white/45 transition-transform", dateOpen && "rotate-180")} />
                  </button>
                  {dateOpen && (
                    <div className="absolute right-0 top-full z-50 mt-1.5 w-56 overflow-hidden rounded-xl border border-white/[0.08] shadow-2xl" style={{ background: "oklch(0.16 0.025 250)" }}>
                      <div className="max-h-64 overflow-y-auto py-1">
                        {[{ value: "all", label: "All" }, ...monthOptions].map((opt) => (
                          <button key={opt.value} onClick={() => { setMonth(opt.value); setDateOpen(false); }}
                            className={cn("flex w-full items-center justify-between px-3 py-2 text-xs transition-colors",
                              opt.value === month ? "bg-indigo-500/10 text-indigo-400" : "text-white/68 hover:bg-white/[0.05] hover:text-white/88")}>
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <button type="button" onClick={() => setFilesOpen(true)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 text-xs text-white/82 transition-colors hover:bg-white/[0.06]">
                  <Upload className="h-3.5 w-3.5 text-cyan-300" /> Files
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── Content ─────────────────────────────────────────────────────────────────── */}
        {tab === "feed" ? (
          analyticsQ.isLoading ? (
            <DashboardSkeleton />
          ) : !hasData ? (
            <EmptyState agentId={agentId} />
          ) : (
            <div className="flex flex-1 overflow-hidden">
              <div className="flex-1 space-y-4 overflow-y-auto p-4">
                <KpiCards summary={summary} propertyCount={propertyCount} onOpenPortfolio={() => setFilesOpen(true)} />
                <IncomeExpensesChart data={bars} />
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <ProfitabilityDonut data={classification} />
                  <VendorSpendList data={vendors} />
                </div>
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <ExpenseCategoriesDonut data={expenseCats} />
                  <RiskScoreList data={risks} />
                </div>
                <ProfitabilityRankingChart data={bars} />
              </div>
              <aside className="hidden w-[340px] shrink-0 border-l border-white/[0.06] xl:flex">
                <InsightRail sections={sections} className="w-full" />
              </aside>
            </div>
          )
        ) : tab === "chat" ? (
          <div className="flex-1 overflow-hidden p-4">
            <FinanceChatPanel agentId={agentId} workerName={workerName} />
          </div>
        ) : (
          <div className="flex-1 overflow-hidden p-4">
            <FinanceHistoryPanel agentId={agentId} />
          </div>
        )}
      </div>

      <FinanceFileManagerDialog agentId={agentId} open={filesOpen} onOpenChange={setFilesOpen} />
    </AppShell>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex-1 space-y-4 overflow-hidden p-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-white/[0.05]" />)}
      </div>
      <div className="h-72 animate-pulse rounded-xl bg-white/[0.05]" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="h-64 animate-pulse rounded-xl bg-white/[0.05]" />
        <div className="h-64 animate-pulse rounded-xl bg-white/[0.05]" />
      </div>
    </div>
  );
}

function EmptyState({ agentId }: { agentId: string }) {
  const uploadRef = useRef<HTMLDivElement>(null);
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto px-4 py-8">
      <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] p-6 sm:p-8" style={{ background: "oklch(0.16 0.02 250)" }} ref={uploadRef}>
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-400/10">
          <Database className="h-5 w-5 text-cyan-300" />
        </div>
        <h2 className="mb-2 text-xl font-semibold text-white/90">No financial data yet</h2>
        <p className="mb-6 text-sm text-white/45">
          Upload a property-portfolio Excel workbook (.xlsx) to unlock the dashboard. Analytics, charts, and
          insights appear automatically once the workbook is processed.
        </p>
        <FinanceFileManager agentId={agentId} />
      </div>
    </div>
  );
}

// Parse "MMM YYYY" month options from file labels / namespaces so the date filter has real choices.
// Mirrors userAnalyticsToDashboard.buildAvailableDateRangeOptions (best-effort; safe when nothing parses).
function monthOptionsFromFiles(
  analytics: FinanceAnalytics | undefined,
  files: { label: string; namespace: string }[] | undefined,
): { value: string; label: string }[] {
  const MONTHS: Record<string, number> = {
    jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
  };
  const tokens = new Set<string>();
  const sources = [
    ...(analytics?.files ?? []).flatMap((f) => [f.label, f.namespace]),
    ...(files ?? []).flatMap((f) => [f.label, f.namespace]),
  ];
  for (const raw of sources) {
    const text = String(raw ?? "");
    let ym: string | null = null;
    const iso = text.match(/\b(20\d{2})[-/](0[1-9]|1[0-2])\b/);
    const named = text.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-_/,]*(20\d{2})\b/i);
    if (iso) ym = `${iso[1]}-${String(iso[2]).padStart(2, "0")}`;
    else if (named) ym = `${named[2]}-${String(MONTHS[named[1].toLowerCase()]).padStart(2, "0")}`;
    if (ym) tokens.add(ym);
  }
  return Array.from(tokens)
    .sort()
    .map((value) => {
      const [y, m] = value.split("-").map(Number);
      const label = new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-GB", { month: "short", year: "numeric" });
      return { value, label };
    });
}
