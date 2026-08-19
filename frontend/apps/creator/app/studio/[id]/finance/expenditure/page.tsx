"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { DrilldownFrame } from "@/components/finance/drilldown-frame";
import { ExpenseList, type ExpenseListFilter } from "@/components/finance/expense-list";

export default function ExpenditurePage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const filter: ExpenseListFilter = useMemo(() => ({
    propertyRef: searchParams.get("property") ?? undefined,
    unitRef: searchParams.get("unit") ?? undefined,
    vendorName: searchParams.get("vendor") ?? undefined,
    category: searchParams.get("category") ?? undefined,
  }), [searchParams]);

  const title = filter.category
    ? `Expense category · ${filter.category}`
    : filter.vendorName
      ? `Expenditure · vendor: ${filter.vendorName}`
      : "Expenditure";

  const subtitle = filter.category
    ? "Properties with spend in this category. Select a property row for invoice-level lines."
    : "Expense rows from the current analytics response.";

  return (
    <DrilldownFrame
      onBack={() => router.push(`/studio/${agentId}/finance`)}
      title={title}
      subtitle={<p className="text-sm text-white/55">{subtitle}</p>}
    >
      <ExpenseList filter={filter} title="All expenses" />
    </DrilldownFrame>
  );
}
