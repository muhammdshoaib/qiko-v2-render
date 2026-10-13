"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@qiko/ui";
import { getAgentAnalytics } from "@/lib/api";
import { ANALYTICS_BUBBLES } from "./investors-data";

const CARD = "rounded-2xl border border-white/[0.08] bg-[#0b0f18]";

const RING: Record<string, string> = {
  growing: "border-indigo-400/80 bg-indigo-500/15 text-indigo-100 shadow-[0_0_28px_rgba(99,102,241,0.25)]",
  established: "border-cyan-400/70 bg-cyan-500/10 text-cyan-50 shadow-[0_0_20px_rgba(34,211,238,0.18)]",
  attention: "border-amber-400/80 bg-amber-500/15 text-amber-50 shadow-[0_0_22px_rgba(251,191,36,0.22)]",
  gap: "border-dashed border-red-400/70 bg-transparent text-slate-400",
};

const CHIP: Record<string, string> = {
  growing: "bg-emerald-400/10 text-emerald-400",
  established: "bg-cyan-400/10 text-cyan-300",
  attention: "bg-amber-400/10 text-amber-300",
  gap: "bg-red-400/10 text-red-300",
};

/** Decorative bar heights for "Today's analytics" when no live agent is linked. */
const SAMPLE_BARS = [28, 44, 36, 58, 42, 70, 52, 64, 38, 76, 48, 60, 34, 72, 50, 66, 40, 55, 46, 68];

export function InvestorsAnalytics({ agentId }: { agentId?: string }) {
  const [active, setActive] = useState(ANALYTICS_BUBBLES[0]?.id ?? "referrals");
  const bubble = ANALYTICS_BUBBLES.find((item) => item.id === active) ?? ANALYTICS_BUBBLES[0];
  const analytics = useQuery({
    queryKey: ["agent-analytics", agentId],
    queryFn: () => getAgentAnalytics(agentId!),
    enabled: !!agentId,
  });

  const liveBars = useMemo(() => {
    if (!analytics.data) return null;
    const calls = Math.max(1, analytics.data.calls || 1);
    const a = analytics.data.input_tokens || 0;
    const b = analytics.data.output_tokens || 0;
    const c = analytics.data.unpriced_calls || 0;
    return [calls, a, b, c].map((n, i) => 20 + ((n / (a + b + calls + 1)) * 60 + i * 7) % 55);
  }, [analytics.data]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] tracking-[0.14em] text-violet-300/90 uppercase">
            Knowledge block · Investors · Analytics
          </p>
          <h1 className="mt-1 text-[26px] font-extrabold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>
            What Investors knows
          </h1>
          <p className="mt-1 max-w-[54ch] text-[13.5px] text-slate-400">
            Every bubble is something the block has learned. Size shows how often it is used. Click one to see the evidence.
          </p>
        </div>
        <span className="inline-flex shrink-0 items-center rounded-full bg-fuchsia-500/15 px-3 py-1 text-[11px] font-semibold tracking-wide text-fuchsia-300 ring-1 ring-fuchsia-400/30">
          NEW · Investors · Analytics tab
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <section className={cn("relative overflow-hidden p-4 sm:p-5", CARD)} aria-label="Knowledge map">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_35%_45%,rgba(99,102,241,0.14),transparent_55%)]" />
          <div className="relative mb-3">
            <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
              Knowledge map
            </h2>
            <p className="text-[12.5px] text-slate-500">
              Investors block · {ANALYTICS_BUBBLES.length} patterns · click a bubble
            </p>
          </div>

          <div className="relative flex min-h-[320px] flex-wrap items-center justify-center gap-3 py-4 sm:gap-4 sm:py-6">
            {ANALYTICS_BUBBLES.map((item) => {
              const on = active === item.id;
              const px = Math.max(72, item.size * 1.15);
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActive(item.id)}
                  aria-pressed={on}
                  className={cn(
                    "flex flex-col items-center justify-center rounded-full border-2 px-2 text-center transition-transform hover:scale-[1.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                    RING[item.tone],
                    on && "scale-[1.06] ring-2 ring-white/35",
                  )}
                  style={{ width: px, height: px }}
                >
                  <span className="text-[11px] font-semibold leading-tight">{item.label}</span>
                  {item.sublabel && (
                    <span className={cn("mt-0.5 text-[9.5px] leading-tight", item.gap ? "text-red-300/80" : "opacity-70")}>
                      {item.sublabel}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <p className="relative text-center text-[11px] text-slate-500">
            Colour = growing, established, needing attention. Dashed red = gap not covered yet.
          </p>
        </section>

        {bubble && (
          <section className={cn("flex flex-col p-4 sm:p-5", CARD)} aria-label="Selected knowledge">
            <p className="font-mono text-[10px] tracking-[0.12em] text-slate-500 uppercase">Selected</p>
            <h2 className="mt-1 text-[18px] font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>
              {bubble.label}
            </h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {bubble.strength && (
                <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-medium", CHIP[bubble.tone])}>
                  {bubble.strength}
                </span>
              )}
              {bubble.agent && bubble.agent !== "—" && (
                <span className="rounded-full bg-sky-400/10 px-2.5 py-0.5 text-[11px] font-medium text-sky-300">
                  {bubble.agent}
                </span>
              )}
            </div>
            <p className="mt-3 text-[13.5px] leading-relaxed text-slate-300">{bubble.summary}</p>

            <div className="mt-4 grid grid-cols-2 gap-2">
              {bubble.stats.map((stat) => (
                <div key={stat.label} className="rounded-xl bg-white/[0.04] px-3 py-2.5">
                  <b className="block text-[18px] font-extrabold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>
                    {stat.value}
                  </b>
                  <span className="text-[11px] text-slate-500">{stat.label}</span>
                </div>
              ))}
            </div>

            <p className="mt-3 text-[11.5px] text-slate-500">{bubble.source}</p>

            <div className="mt-auto flex flex-wrap gap-2 pt-5">
              <Link
                href="/studio/intelligence?tab=channels&surface=claude"
                className="inline-flex min-h-10 items-center rounded-lg bg-indigo-500 px-3.5 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                Simulate in Claude
              </Link>
              <button
                type="button"
                disabled={!!bubble.gap}
                className="inline-flex min-h-10 items-center rounded-lg border border-white/15 px-3.5 text-[13px] font-semibold text-slate-200 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
              >
                Make it a rule
              </button>
            </div>
          </section>
        )}
      </div>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="Today's analytics">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
              Today&apos;s analytics
            </h2>
            <p className="text-[12.5px] text-slate-500">Existing charts stay below the knowledge map</p>
          </div>
          {agentId && analytics.isError && (
            <button type="button" className="text-[12px] text-cyan-300 underline" onClick={() => analytics.refetch()}>
              Retry live usage
            </button>
          )}
        </div>

        <div className="flex h-[120px] items-end gap-1.5 rounded-xl bg-white/[0.03] px-3 py-3 sm:gap-2">
          {(liveBars ?? SAMPLE_BARS).map((h, i) => (
            <span
              key={i}
              className="min-w-0 flex-1 rounded-t-sm bg-sky-400/70"
              style={{ height: `${h}%` }}
              title={agentId && analytics.data ? "Live usage signal" : "Sample chart"}
            />
          ))}
        </div>

        {agentId && analytics.data && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["Calls", analytics.data.calls],
              ["Input tokens", analytics.data.input_tokens],
              ["Output tokens", analytics.data.output_tokens],
              ["Unpriced", analytics.data.unpriced_calls],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-lg bg-white/[0.03] px-3 py-2">
                <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
                <p className="text-sm font-semibold text-white">{Number(value).toLocaleString()}</p>
              </div>
            ))}
          </div>
        )}
        {!agentId && (
          <p className="mt-2 text-[12px] text-slate-500">
            Sample bars for the demo. Connect a live worker to this block to show call and token volume.
          </p>
        )}
      </section>
    </div>
  );
}
