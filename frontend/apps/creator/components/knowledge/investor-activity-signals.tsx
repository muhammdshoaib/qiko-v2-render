"use client";

import { useMemo, useState } from "react";
import { cn } from "@qiko/ui";

type Kind = "activity" | "signal";
type Filter = "all" | Kind;

type Row = {
  id: string;
  kind: Kind;
  title: string;
  detail: string;
  when: string;
  investor?: string;
};

/** Sample events mirroring Joseph Mews app activity + intent signals (until Creator binds live GETs). */
const ROWS: Row[] = [
  {
    id: "a1",
    kind: "activity",
    title: "Property viewed · Lombe House / Derby",
    detail: "Repeat open in investor app · calculator step opened",
    when: "Today, 09:38",
    investor: "inv-lombe-01",
  },
  {
    id: "s1",
    kind: "signal",
    title: "High intent · Lombe House",
    detail: "Repeat views clustered as purchase interest · no outreach sent",
    when: "Today, 09:40",
    investor: "inv-lombe-01",
  },
  {
    id: "a2",
    kind: "activity",
    title: "Screen · Portfolio",
    detail: "Investor opened portfolio holdings screen",
    when: "Today, 08:12",
    investor: "inv-4821",
  },
  {
    id: "a3",
    kind: "activity",
    title: "Calculator · yield",
    detail: "Net yield calculator completed",
    when: "Yesterday, 16:05",
    investor: "inv-9012",
  },
  {
    id: "s2",
    kind: "signal",
    title: "Intent signal · off-plan enquiry",
    detail: "5% deposit questions in session · strength medium",
    when: "Yesterday, 16:22",
    investor: "inv-9012",
  },
  {
    id: "a4",
    kind: "activity",
    title: "Screen · Developments",
    detail: "Browse session · 3 developments",
    when: "Yesterday, 14:40",
    investor: "inv-2201",
  },
  {
    id: "s3",
    kind: "signal",
    title: "Quiet listing flag",
    detail: "7-day gap in views on two listings · recorded only",
    when: "2 days ago",
    investor: "—",
  },
];

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "activity", label: "Activity" },
  { id: "signal", label: "Signals" },
];

export function InvestorActivitySignals() {
  const [filter, setFilter] = useState<Filter>("all");
  const items = useMemo(
    () => (filter === "all" ? ROWS : ROWS.filter((row) => row.kind === filter)),
    [filter],
  );

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
          Investor activity &amp; signals
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Events from the Joseph Mews investor app and intent signals captured for this knowledge block.
        </p>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter activity and signals">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            onClick={() => setFilter(item.id)}
            className={cn(
              "rounded-full border px-3 py-1 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
              filter === item.id
                ? "border-white/25 bg-white/10 text-white"
                : "border-white/[0.08] text-slate-400 hover:text-white",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 px-6 py-12 text-center text-sm text-slate-400">
          No events in this filter.
        </div>
      ) : (
        <ul className="divide-y divide-white/[0.05] rounded-2xl border border-white/[0.06] bg-[#0b0f18]">
          {items.map((row) => (
            <li key={row.id} className="flex items-start justify-between gap-3 px-4 py-3.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "rounded-md px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.06em]",
                      row.kind === "signal"
                        ? "bg-amber-400/10 text-amber-300"
                        : "bg-sky-400/10 text-sky-300",
                    )}
                  >
                    {row.kind}
                  </span>
                  <p className="text-sm font-medium text-white">{row.title}</p>
                </div>
                <p className="mt-1 text-[12.5px] text-slate-400">{row.detail}</p>
                {row.investor && row.investor !== "—" && (
                  <p className="mt-1 font-mono text-[11px] text-slate-500">{row.investor}</p>
                )}
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
