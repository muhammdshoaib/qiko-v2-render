"use client";

import { useSearchParams } from "next/navigation";
import { KpiDetailPanel } from "@/components/finance/kpi-detail-panel";
import { PortfolioPanel } from "@/components/finance/portfolio-panel";

export default function BreakdownPage() {
  const searchParams = useSearchParams();
  const view = searchParams.get("view") ?? "properties";

  if (view === "income") return <KpiDetailPanel metric="totalIncome" />;
  if (view === "expenses") return <KpiDetailPanel metric="totalExpenses" />;
  if (view === "profit") return <KpiDetailPanel metric="netProfit" />;

  return <PortfolioPanel />;
}
