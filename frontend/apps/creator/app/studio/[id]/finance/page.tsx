"use client";

import { useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Database, Search } from "lucide-react";
import {
  ExpenseCategoriesDonut, IncomeExpensesChart, ProfitabilityDonut, ProfitabilityRankingChart,
  RiskScoreList, VendorSpendList,
} from "@/components/finance/charts";
import { FinanceFileManager } from "@/components/finance/file-manager";
import { InsightRail } from "@/components/finance/insight-rail";
import { KpiCards } from "@/components/finance/kpi-cards";
import { useFinance } from "@/components/finance/finance-context";
import {
  classificationDonut, expenseCategoryDonut, normalizeFinanceSummary, propertyBars,
  riskRows, trendSections, vendorRows,
} from "@/components/finance/utils";
import type { FinanceAnalytics } from "@/lib/api";

const BG = "oklch(0.16 0.02 250)";

export default function FinanceDashboardPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const { analytics, isLoading } = useFinance();
  const [search, setSearch] = useState("");

  const hasData = (analytics?.properties?.length ?? 0) > 0 || (analytics?.totalRows ?? 0) > 0;

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

  const to = (path: string) => router.push(`/studio/${agentId}/finance${path}`);

  const handleKpiClick = (key: string) => {
    if (key === "income") return to("/breakdown?view=income");
    if (key === "expenses") return to("/expenditure");
    if (key === "profit") return to("/breakdown?view=profit");
    if (key === "properties") return to("/breakdown?view=properties");
  };

  const handlePropertyClick = (ref: string) => to(`/property/${encodeURIComponent(ref)}`);
  const handleVendorClick = (name: string) => to(`/vendor/${encodeURIComponent(name)}`);
  const handleCategoryClick = (cat: string) => to(`/expenditure?category=${encodeURIComponent(cat)}`);
  const handleClassClick = () => to("/breakdown?view=profit");

  if (isLoading) return <DashboardSkeleton />;
  if (!hasData) return <EmptyState agentId={agentId} />;

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="relative w-full sm:w-[min(26rem,42vw)]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/45" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search properties..."
              className="h-9 w-full rounded-lg border border-white/[0.08] bg-white/[0.04] pl-8 pr-3 text-xs text-white/85 outline-none placeholder:text-white/45 focus:border-indigo-400/45"
            />
          </div>
        </div>

        <KpiCards summary={summary} propertyCount={propertyCount} onOpenPortfolio={() => handleKpiClick("properties")} onKpiClick={handleKpiClick} />
        <IncomeExpensesChart data={bars} onPropertyClick={handlePropertyClick} />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ProfitabilityDonut data={classification} onClassClick={handleClassClick} />
          <VendorSpendList data={vendors} onVendorClick={handleVendorClick} />
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ExpenseCategoriesDonut data={expenseCats} onCategoryClick={handleCategoryClick} />
          <RiskScoreList data={risks} onPropertyClick={handlePropertyClick} />
        </div>
        <ProfitabilityRankingChart data={bars} onPropertyClick={handlePropertyClick} />
      </div>
      <aside className="hidden w-[340px] shrink-0 border-l border-white/[0.06] xl:flex">
        <InsightRail sections={sections} className="w-full" />
      </aside>
    </div>
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
      <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] p-6 sm:p-8" style={{ background: BG }} ref={uploadRef}>
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
