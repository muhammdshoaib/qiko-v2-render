"use client";

import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { ExpenseList, type ExpenseListFilter } from "@/components/finance/expense-list";

export default function ExpenditurePage() {
  const searchParams = useSearchParams();
  const filter: ExpenseListFilter = useMemo(() => ({
    propertyRef: searchParams.get("property") ?? undefined,
    unitRef: searchParams.get("unit") ?? undefined,
    vendorName: searchParams.get("vendor") ?? undefined,
    category: searchParams.get("category") ?? undefined,
  }), [searchParams]);

  const titleParts = ["Expenditure"];
  if (filter.vendorName) titleParts.push(`vendor: ${filter.vendorName}`);
  if (filter.category) titleParts.push(`category: ${filter.category}`);
  if (filter.propertyRef) titleParts.push("property");
  if (filter.unitRef) titleParts.push("unit");

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold text-white">{titleParts.join(" - ")}</h1>
      <ExpenseList filter={filter} title="All expenses" />
    </div>
  );
}
