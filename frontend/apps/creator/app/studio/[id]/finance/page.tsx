"use client";

import { useMemo, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { BarChart3, Database, Upload } from "lucide-react";
import {
  ExpenseCategoriesDonut, IncomeExpensesChart, ProfitabilityDonut, ProfitabilityRankingChart,
  RiskScoreList, VendorSpendList,
} from "@/components/finance/charts";
import { FinanceFileManager } from "@/components/finance/file-manager";
import { KpiCards } from "@/components/finance/kpi-cards";
import { useFinance } from "@/components/finance/finance-context";
import {
  classificationDonut, expenseCategoryDonut, normalizeFinanceSummary, propertyBars,
  riskRows, vendorRows,
} from "@/components/finance/utils";
import type { FinanceAnalytics } from "@/lib/api";

const BG = "oklch(0.16 0.02 250)";

export default function FinanceDashboardPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const { analytics, isLoading, search, setMonth } = useFinance();

  const hasData = (analytics?.properties?.length ?? 0) > 0 || (analytics?.totalRows ?? 0) > 0;

  const filteredAnalytics = useMemo<FinanceAnalytics | undefined>(() => {
    if (!analytics) return analytics;
    const term = search.trim().toLowerCase();
    if (!term) return analytics;
    return {
      ...analytics,
      properties: (analytics.properties ?? []).filter((p) => String(p.name ?? p.propertyId ?? p.propertyRef ?? "").toLowerCase().includes(term)),
    };
  }, [analytics, search]);

  const summary = useMemo(() => normalizeFinanceSummary(analytics?.summary), [analytics]);
  const propertyCount = summary.propertyCount || (analytics?.properties?.filter((p) => (p.income ?? 0) || (p.expenses ?? 0)).length ?? 0);

  const bars = useMemo(() => propertyBars(filteredAnalytics), [filteredAnalytics]);
  const classification = useMemo(() => classificationDonut(filteredAnalytics), [filteredAnalytics]);
  const vendors = useMemo(() => vendorRows(filteredAnalytics), [filteredAnalytics]);
  const expenseCats = useMemo(() => expenseCategoryDonut(filteredAnalytics), [filteredAnalytics]);
  const risks = useMemo(() => riskRows(filteredAnalytics), [filteredAnalytics]);

  const to = (path: string) => router.push(`/studio/${agentId}/finance${path}`);

  const handleKpiClick = (key: string) => {
    if (key === "income") return to("/breakdown?view=income");
    if (key === "expenses") return to("/breakdown?view=expenses");
    if (key === "profit") return to("/breakdown?view=profit");
    if (key === "properties") return to("/breakdown?view=properties");
  };

  const handlePropertyClick = (ref: string) => to(`/property/${encodeURIComponent(ref)}`);
  const handleVendorClick = (name: string) => to(`/vendor/${encodeURIComponent(name)}`);
  const handleCategoryClick = (cat: string) => to(`/expenditure?category=${encodeURIComponent(cat)}`);
  const handleClassClick = () => to("/breakdown?view=profit");

  if (isLoading) return <DashboardSkeleton />;
  if (!hasData) return <EmptyState agentId={agentId} onUploaded={() => setMonth("all")} />;

  return (
    <div className="flex-1 space-y-4 overflow-y-auto p-4">
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
  );
}

function DashboardSkeleton() {
  return (
    <div className="h-full space-y-4 p-4 animate-pulse">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-28 rounded-xl bg-white/[0.06]" />)}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="h-72 rounded-xl bg-white/[0.06]" />
        <div className="h-72 rounded-xl bg-white/[0.06]" />
      </div>
      <div className="h-56 rounded-xl bg-white/[0.06]" />
    </div>
  );
}

function EmptyState({ agentId, onUploaded }: { agentId: string; onUploaded?: () => void }) {
  const uploadRef = useRef<HTMLDivElement>(null);
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto px-4 py-8">
      <div className="w-full max-w-2xl rounded-2xl border border-white/[0.08] p-6 sm:p-8" style={{ background: BG }} ref={uploadRef}>
        <h2 className="mb-2 text-xl font-semibold text-white/90 sm:text-2xl">No financial data yet</h2>
        <p className="mb-6 text-sm text-white/45">
          Upload a property-portfolio Excel workbook (.xlsx). Dashboard insights appear automatically once the workbook is processed.
        </p>
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
            <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-400/10">
              <Upload className="h-4 w-4 text-cyan-300" />
            </div>
            <p className="mb-1 text-xs font-semibold text-white/80">Step 1</p>
            <p className="text-xs text-white/45">Choose an .xlsx property portfolio workbook.</p>
          </div>
          <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
            <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-400/10">
              <Database className="h-4 w-4 text-indigo-300" />
            </div>
            <p className="mb-1 text-xs font-semibold text-white/80">Step 2</p>
            <p className="text-xs text-white/45">Upload and wait for the workbook to be indexed.</p>
          </div>
          <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
            <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-green-400/10">
              <BarChart3 className="h-4 w-4 text-green-300" />
            </div>
            <p className="mb-1 text-xs font-semibold text-white/80">Step 3</p>
            <p className="text-xs text-white/45">Charts, KPIs, and trends appear on this dashboard.</p>
          </div>
        </div>
        <FinanceFileManager agentId={agentId} onUploaded={onUploaded} />
      </div>
    </div>
  );
}
