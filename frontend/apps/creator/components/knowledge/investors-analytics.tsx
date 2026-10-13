"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { getAgentAnalytics } from "@/lib/api";
import { ANALYTICS_BUBBLES, BUBBLE_DETAIL } from "./investors-data";

const CARD = "rounded-2xl border border-white/[0.06] bg-white/[0.015]";

const TONE: Record<string, string> = {
  growing: "bg-emerald-400/80 shadow-[0_0_24px_rgba(52,211,153,0.35)]",
  established: "bg-cyan-400/70 shadow-[0_0_18px_rgba(34,211,238,0.25)]",
  attention: "bg-amber-400/80 shadow-[0_0_22px_rgba(251,191,36,0.3)]",
  gap: "border border-dashed border-white/30 bg-transparent",
};

const CHART_STATS: { key: "calls" | "input_tokens" | "output_tokens" | "unpriced_calls"; label: string }[] = [
  { key: "calls", label: "Total calls" },
  { key: "input_tokens", label: "Input tokens" },
  { key: "output_tokens", label: "Output tokens" },
  { key: "unpriced_calls", label: "Calls pending pricing data" },
];

export function InvestorsAnalytics({ agentId }: { agentId?: string }) {
  const [active, setActive] = useState(ANALYTICS_BUBBLES[0]?.id ?? null);
  const detail = active ? BUBBLE_DETAIL[active] : null;
  const bubble = ANALYTICS_BUBBLES.find((item) => item.id === active);
  const analytics = useQuery({
    queryKey: ["agent-analytics", agentId],
    queryFn: () => getAgentAnalytics(agentId!),
    enabled: !!agentId,
  });

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white sm:text-2xl" style={{ fontFamily: "var(--font-display)" }}>
            Analytics
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Knowledge map for Investors — bubble size is how often it is used; colour is growing, established, needing attention, or a gap.
          </p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      <section className={cn("relative overflow-hidden p-4 sm:p-6", CARD)} aria-label="Investors knowledge map">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_30%_40%,rgba(99,102,241,0.12),transparent_55%)]" />
        <div className="relative flex min-h-[280px] flex-wrap items-center justify-center gap-4 py-6 sm:gap-6">
          {ANALYTICS_BUBBLES.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setActive(item.id)}
              aria-pressed={active === item.id}
              className={cn(
                "flex flex-col items-center justify-center rounded-full text-center transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                TONE[item.tone],
                active === item.id && "ring-2 ring-white/40",
              )}
              style={{ width: item.size * 1.35, height: item.size * 1.35 }}
            >
              <span className={cn("px-2 text-[11px] font-semibold leading-tight", item.gap ? "text-slate-400" : "text-slate-950")}>
                {item.label}
              </span>
              {!item.gap && <span className="mt-0.5 text-[10px] text-slate-900/70">used {item.used}×</span>}
              {item.gap && <span className="mt-0.5 text-[10px] text-slate-500">gap</span>}
            </button>
          ))}
        </div>
        <p className="relative text-center text-[11px] text-slate-500">
          Same bubble style as Pulse, showing what is inside Investors. Dashed = nothing covers it yet.
        </p>
      </section>

      {bubble && detail && (
        <section className={cn("p-4 sm:p-5", CARD)} aria-label="Selected knowledge">
          <h2 className="text-[15px] font-semibold text-white">{bubble.label}</h2>
          <p className="mt-1 text-[12px] text-slate-500">From {detail.from}</p>
          <p className="mt-2 text-[13.5px] text-slate-300">{detail.evidence}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              href="/studio/intelligence?tab=channels&surface=claude"
              className="rounded-lg bg-indigo-500 px-3 py-2 text-[12px] font-medium text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
            >
              Simulate in Claude
            </Link>
            <button
              type="button"
              className="rounded-lg border border-white/10 px-3 py-2 text-[12px] text-slate-300 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
            >
              Make it a rule
            </button>
          </div>
        </section>
      )}

      <section aria-label="Usage charts">
        <h2 className="mb-3 text-sm font-semibold text-white">Usage charts</h2>
        <p className="mb-3 text-[12.5px] text-slate-500">Today&apos;s analytics charts stay underneath the knowledge map.</p>
        {!agentId ? (
          <p className="text-sm text-slate-400">Connect a live worker to this block to show call and token volume.</p>
        ) : analytics.isError ? (
          <p className="text-sm text-slate-300">
            Couldn&apos;t load usage analytics.{" "}
            <button type="button" className="text-cyan-300 underline" onClick={() => analytics.refetch()}>Retry</button>
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {CHART_STATS.map((stat) => (
              <div key={stat.key} className={cn("p-4", CARD)}>
                <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{stat.label}</p>
                <p className="mt-2 text-2xl font-bold text-white">
                  {analytics.isLoading ? "…" : (analytics.data?.[stat.key] ?? 0).toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
