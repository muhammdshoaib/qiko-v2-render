"use client";

import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { PropertyList } from "@/components/finance/property-list";

type View = "income" | "profit" | "outstanding" | "properties";

const VIEW_LABELS: Record<View, string> = {
  income: "Properties by income",
  profit: "Properties by profit",
  outstanding: "Properties by outstanding",
  properties: "All properties",
};

export default function BreakdownPage() {
  const searchParams = useSearchParams();
  const view = (searchParams.get("view") ?? "properties") as View;
  const label = VIEW_LABELS[view] ?? VIEW_LABELS.properties;

  const sortBy = useMemo<"name" | "income" | "profit" | "outstanding">(() => {
    if (view === "income" || view === "profit" || view === "outstanding") return view;
    return "name";
  }, [view]);

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold text-white">{label}</h1>
      <PropertyList sortBy={sortBy} title={label} />
    </div>
  );
}
