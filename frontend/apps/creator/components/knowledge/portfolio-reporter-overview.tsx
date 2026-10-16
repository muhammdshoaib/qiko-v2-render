"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ListTodo, FileSearch } from "lucide-react";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { addSharedPulseAction } from "@/lib/pulse-action-store";
import {
  PORTFOLIO_BLOCK,
  PORTFOLIO_CAPTURED,
  PORTFOLIO_FUNNEL,
  type PortfolioOverviewInsight,
} from "./portfolio-reporter-data";

const CARD = "rounded-2xl border border-slate-200 bg-white shadow-sm";

const FEED_CHIP: Record<string, string> = {
  blue: "bg-sky-50 text-sky-700",
  warn: "bg-amber-50 text-amber-700",
  good: "bg-emerald-50 text-emerald-700",
};

export function PortfolioReporterOverview() {
  const [selectedId, setSelectedId] = useState<string | null>(PORTFOLIO_CAPTURED[0]?.id ?? null);
  const selected = PORTFOLIO_CAPTURED.find((i) => i.id === selectedId) ?? null;

  const addAction = (insight: PortfolioOverviewInsight) => {
    addSharedPulseAction({
      title: `Follow up · ${insight.title}`,
      insightTitle: insight.title,
      source: "Portfolio Reporter · Overview",
    });
    toast.success("Added to action list", {
      description: "Open Pulse to track To do → In progress → Done.",
      action: { label: "Open Pulse", onClick: () => { window.location.href = "/dashboard?view=insights"; } },
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 sm:text-2xl" style={{ fontFamily: "var(--font-display)" }}>
            Overview
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Holdings-backed insights and items that need a person — not automated outcomes.
          </p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="From holdings to insight cards">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">From holdings to insight cards</h2>
            <p className="text-[12px] text-slate-500">Advised investors → readable holdings → cards → concentration</p>
          </div>
        </div>
        <ol className="grid gap-2 sm:grid-cols-4">
          {PORTFOLIO_FUNNEL.map((step) => (
            <li
              key={step.id}
              className={cn(
                "rounded-xl border px-3 py-3",
                step.actOn ? "border-indigo-200 bg-indigo-50/50" : "border-slate-200 bg-slate-50/80",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] uppercase tracking-wider text-slate-500">{step.label}</p>
                <HonestyBadge kind={step.honesty} className="scale-90" />
              </div>
              <p className="mt-1 text-2xl font-bold text-slate-900">{step.count.toLocaleString()}</p>
              <p className="mt-1 text-[11px] text-slate-500">{step.system}</p>
              {step.actOn && <p className="mt-2 text-[11px] font-medium text-indigo-600">Primary output</p>}
            </li>
          ))}
        </ol>
      </section>

      <section className={cn("overflow-hidden", CARD)} aria-label="Insights">
        <div className="border-b border-slate-100 px-4 py-3 sm:px-5">
          <h2 className="text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
            Insights
          </h2>
          <p className="mt-0.5 text-[12.5px] text-slate-500">
            Observed from holdings — not completed outcomes. Select a row to open detail.
          </p>
        </div>
        <div className="grid lg:grid-cols-[minmax(0,1.05fr)_minmax(300px,0.95fr)]">
          <ul className="divide-y divide-slate-100 lg:border-r lg:border-slate-100">
            {PORTFOLIO_CAPTURED.map((item) => {
              const on = item.id === selectedId;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={cn(
                      "grid w-full grid-cols-[32px_minmax(0,1fr)] gap-3 border-l-2 px-4 py-3.5 text-left sm:px-5",
                      on
                        ? "border-l-indigo-500 bg-indigo-50/40"
                        : "border-l-transparent hover:bg-slate-50/80",
                    )}
                  >
                    <span className="grid size-8 place-items-center rounded-full bg-indigo-50 font-mono text-[10px] font-medium text-indigo-700">
                      {item.initials}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[13.5px] font-semibold text-slate-900">{item.title}</span>
                      <span className="mt-0.5 block text-[12.5px] text-slate-500">{item.evidence}</span>
                      <span className="mt-1.5 flex flex-wrap items-center gap-2">
                        <span className={cn("rounded-md px-2 py-0.5 text-[10px] font-medium", FEED_CHIP[item.tone])}>
                          {item.chip}
                        </span>
                        <HonestyBadge kind={item.honesty} className="scale-90" />
                        <span className="font-mono text-[10.5px] text-slate-500">{item.when}</span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          <div
            className="flex min-h-[320px] flex-col bg-white max-lg:border-t max-lg:border-slate-100"
            aria-label="Insight detail"
          >
            {!selected ? (
              <div className="flex flex-1 items-center justify-center px-5 text-sm text-slate-500">
                Select an insight to view evidence.
              </div>
            ) : (
              <>
                <div className="px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[11px] font-semibold tracking-[0.08em] text-indigo-600 uppercase">Insight</p>
                    <HonestyBadge kind={selected.honesty} />
                  </div>
                  <h3 className="mt-1 text-[17px] font-bold tracking-[-0.02em] text-slate-900">{selected.title}</h3>
                  <p className="mt-1 text-[12.5px] text-slate-500">
                    {PORTFOLIO_BLOCK.role} · {selected.when}
                  </p>
                </div>
                <div className="flex-1 space-y-4 overflow-y-auto border-t border-slate-100 bg-slate-50/40 px-5 py-4">
                  <p className="text-[14px] leading-relaxed text-slate-700">{selected.detail}</p>
                  <div>
                    <p className="text-[12px] font-semibold text-slate-900">Supporting evidence</p>
                    <ul className="mt-2 space-y-1.5">
                      {selected.evidenceLines.map((line) => (
                        <li key={line} className="rounded-xl border border-slate-200/80 bg-white px-3 py-2 text-[12.5px] text-slate-600">
                          {line}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 px-3 py-2.5">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600">Recommendation</p>
                    <p className="mt-1 text-[13px] text-slate-700">{selected.recommendation}</p>
                  </div>
                </div>
                <div className="border-t border-slate-100 bg-white px-5 py-4">
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => document.getElementById("pr-insight-evidence")?.scrollIntoView({ behavior: "smooth" })}
                      className="inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-[13px] font-semibold text-slate-700 hover:bg-slate-50"
                    >
                      <FileSearch className="size-4" />
                      View evidence
                    </button>
                    <button
                      type="button"
                      onClick={() => addAction(selected)}
                      className="inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-3 text-[13px] font-semibold text-white hover:bg-indigo-700"
                    >
                      <ListTodo className="size-4" />
                      Add to action list
                    </button>
                  </div>
                  <p id="pr-insight-evidence" className="mt-3 text-[11px] text-slate-500">
                    Actions stay with you. No contact, trade advice, or payments.{" "}
                    <Link href="/dashboard?view=insights" className="font-medium text-indigo-600 hover:underline">
                      Open Pulse action list
                    </Link>
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      </section>

      <section className={cn("p-4 sm:p-5", CARD)}>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600">Guardrail</p>
        <h2 className="mt-1 text-[15px] font-semibold text-slate-900">No contact, trade advice, or payments</h2>
        <p className="mt-1 max-w-[52ch] text-[13px] text-slate-500">
          Portfolio Reporter writes cards into the investor app. A person still decides any follow-up.
        </p>
      </section>
    </div>
  );
}
