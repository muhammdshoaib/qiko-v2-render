"use client";

import { useMemo, useState } from "react";
import { cn } from "@qiko/ui";
import { PORTFOLIO_OBSERVABILITY } from "./portfolio-reporter-data";

type Kind = "insight" | "action" | "blocked";
type Filter = "all" | Kind;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "insight", label: "Insights" },
  { id: "action", label: "Actions" },
  { id: "blocked", label: "Blocked" },
];

const KIND_CHIP: Record<Kind, string> = {
  insight: "bg-indigo-50 text-indigo-700",
  action: "bg-sky-50 text-sky-700",
  blocked: "bg-red-50 text-red-700",
};

export function PortfolioReporterObservability() {
  const [filter, setFilter] = useState<Filter>("all");
  const items = useMemo(
    () => (filter === "all" ? PORTFOLIO_OBSERVABILITY : PORTFOLIO_OBSERVABILITY.filter((row) => row.kind === filter)),
    [filter],
  );

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>
          Portfolio insights &amp; actions
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Insight cards written from holdings, completed actions, and hard-wall blocks for this knowledge block.
        </p>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter portfolio events">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            onClick={() => setFilter(item.id)}
            className={cn(
              "rounded-full border px-3 py-1 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
              filter === item.id
                ? "border-border bg-slate-100 text-foreground"
                : "border-border text-slate-500 hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border px-6 py-12 text-center text-sm text-slate-400">
          No events in this filter.
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-2xl border border-border bg-card">
          {items.map((row) => (
            <li key={row.id} className="flex items-start justify-between gap-3 px-4 py-3.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded-md px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.06em]", KIND_CHIP[row.kind])}>
                    {row.kind}
                  </span>
                  <p className="text-sm font-medium text-foreground">{row.title}</p>
                </div>
                <p className="mt-1 text-[12.5px] text-slate-400">{row.detail}</p>
              </div>
              <time className="shrink-0 text-[11px] text-slate-500">{row.when}</time>
            </li>
          ))}
        </ul>
      )}

      <p className="text-[12px] text-slate-500">{items.length} events shown.</p>
    </div>
  );
}
