"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { PORTFOLIO_CAPTURED, PORTFOLIO_FUNNEL } from "./portfolio-reporter-data";

const CARD = "rounded-2xl border border-white/[0.08] bg-[#0b0f18]";

const FEED_CHIP: Record<string, string> = {
  blue: "bg-sky-400/10 text-sky-300",
  warn: "bg-amber-400/10 text-amber-300",
  good: "bg-emerald-400/10 text-emerald-400",
};

export function PortfolioReporterOverview() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white sm:text-2xl" style={{ fontFamily: "var(--font-display)" }}>
            Overview
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            How Portfolio Reporter turns holdings into grounded insight cards.
          </p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="From holdings to insight cards">
        <div className="mb-4 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-white">From holdings to insight cards</h2>
          <p className="text-[11px] text-slate-500">Each step&apos;s number comes from a connected system</p>
        </div>
        <ol className="grid gap-2 sm:grid-cols-4">
          {PORTFOLIO_FUNNEL.map((step) => (
            <li
              key={step.id}
              className={cn(
                "rounded-xl border px-3 py-3",
                step.actOn ? "border-cyan-400/40 bg-cyan-500/10" : "border-white/[0.06] bg-white/[0.02]",
                !step.connected && "border-dashed border-red-400/40",
              )}
            >
              <p className="text-[11px] uppercase tracking-wider text-slate-500">{step.label}</p>
              <p className="mt-1 text-2xl font-bold text-white">{step.count.toLocaleString()}</p>
              <p className={cn("mt-1 text-[11px]", step.connected ? "text-slate-400" : "text-red-300")}>
                {step.system}
              </p>
              {step.actOn && <p className="mt-2 text-[11px] font-medium text-cyan-300">Primary output</p>}
            </li>
          ))}
        </ol>
      </section>

      <section className={cn("flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5", CARD)}>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-400">Guardrail</p>
          <h2 className="mt-1 text-[15px] font-semibold text-white">No contact, trade advice, or payments</h2>
          <p className="mt-1 max-w-[52ch] text-[13px] text-slate-400">
            Portfolio Reporter writes cards into the investor app. A person still decides any follow-up.
          </p>
        </div>
        <Link
          href="/studio/intelligence?tab=channels&surface=claude"
          className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-indigo-500 px-4 text-sm font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
        >
          <Sparkles className="size-4" /> Simulate in Claude
        </Link>
      </section>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="Recent insight activity">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
            Recent insight activity
          </h2>
        </div>
        <ul className="divide-y divide-white/[0.06]">
          {PORTFOLIO_CAPTURED.map((item) => (
            <li key={item.id} className="grid grid-cols-[32px_minmax(0,1fr)] gap-3 py-3 first:pt-0 last:pb-0">
              <span className="grid size-8 place-items-center rounded-full bg-cyan-500/15 font-mono text-[10px] font-medium text-cyan-300">
                {item.initials}
              </span>
              <div className="min-w-0">
                <p className="text-[13.5px] font-semibold text-white">{item.title}</p>
                <p className="mt-0.5 text-[12.5px] text-slate-500">{item.evidence}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <span className={cn("rounded-md px-2 py-0.5 text-[10px] font-medium", FEED_CHIP[item.tone])}>
                    · {item.chip}
                  </span>
                  <span className="font-mono text-[10.5px] text-slate-500">{item.when}</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
