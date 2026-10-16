"use client";

import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { cn } from "@qiko/ui";
import type { GrowthPoint } from "./record-summary";

export function KnowledgeGrowth({
  points,
  selected,
  onSelect,
  compact = false,
}: {
  points: GrowthPoint[];
  selected: string | null;
  onSelect: (month: string) => void;
  compact?: boolean;
}) {
  const max = Math.max(...points.map((point) => point.notes), 1);
  const current = points.find((point) => point.month === selected) ?? null;

  return (
    <section className={compact ? "rounded-2xl border border-border bg-card px-4 py-4 sm:px-5" : undefined}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2
            className="text-[15px] font-semibold tracking-[-0.01em] text-foreground"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Knowledge over time
          </h2>
          <p className="mt-0.5 text-[12.5px] text-slate-400">
            Notes and decisions written to the company record — not a score. Click a month to inspect.
          </p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      <ol className="relative mt-5 flex items-end justify-between gap-1">
        <span className="pointer-events-none absolute top-[22px] right-8 left-8 h-px bg-slate-100" aria-hidden />
        {points.map((point) => {
          const on = selected === point.month;
          const size = 12 + (point.notes / max) * 20;
          return (
            <li key={point.month} className="relative z-[1] flex flex-1 flex-col items-center">
              <button
                type="button"
                aria-pressed={on}
                aria-label={`${point.month}: ${point.notes} ${point.notes === 1 ? "note" : "notes"} on record. ${point.captures[0]?.title ?? ""}`}
                onClick={() => onSelect(point.month)}
                className="flex min-h-11 flex-col items-center gap-1.5 rounded-xl px-1 text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                <span
                  className={cn(
                    "rounded-full border transition duration-200 motion-reduce:transition-none",
                    on
                      ? "border-cyan-300 bg-indigo-500/35 shadow-[0_0_16px_-4px_rgba(34,211,238,.75)]"
                      : "border-indigo-400/40 bg-indigo-500/25 hover:border-indigo-400/50",
                    point.awaiting && !on && "motion-safe:animate-[qiko-breathe_2.8s_ease-in-out_infinite]",
                  )}
                  style={{ width: size, height: size }}
                />
                <span className={cn("font-mono text-[11px] tracking-[0.08em] uppercase", on && "text-foreground")}>
                  {point.month}
                </span>
                <span className="font-mono text-[10px] text-slate-500">
                  {point.notes} {point.notes === 1 ? "note" : "notes"}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {current && (
        <div className="mt-4 rounded-xl border border-border bg-muted px-3.5 py-3">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">
            {current.month} · what was captured
          </p>
          <ul className="mt-2 space-y-2.5">
            {current.captures.map((item) => (
              <li key={item.title}>
                <p className="text-[13.5px] font-medium text-foreground">{item.title}</p>
                <p className="mt-0.5 text-[12.5px] leading-relaxed text-slate-400">{item.evidence}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
