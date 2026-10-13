"use client";

import Link from "next/link";
import { ArrowRight, Network, Sparkles } from "lucide-react";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import {
  BLOCK_AGENTS,
  CAPTURED_KNOWLEDGE,
  FUNNEL_STEPS,
  INVESTORS_BLOCK,
} from "./investors-data";

const CARD = "rounded-2xl border border-white/[0.06] bg-white/[0.015]";

export function InvestorsOverview() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white sm:text-2xl" style={{ fontFamily: "var(--font-display)" }}>
            Overview
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            How this knowledge block is working — from connected systems to the next move.
          </p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      <div className={cn("grid grid-cols-2 gap-3 p-4 sm:grid-cols-4 sm:p-5", CARD)}>
        {[
          { label: "Value this month", value: INVESTORS_BLOCK.valueThisMonth, hint: INVESTORS_BLOCK.valueHint },
          { label: "Conversations", value: String(INVESTORS_BLOCK.conversations), hint: "Illustrative · grounded chats and signals." },
          { label: "Patterns to date", value: String(INVESTORS_BLOCK.patternsToDate), hint: "Illustrative · recorded learnings." },
          { label: "Handed to CRM", value: String(INVESTORS_BLOCK.handedToCrm), hint: "Illustrative · CRM is not connected yet." },
        ].map((item) => (
          <div key={item.label} className="min-w-0">
            <p className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{item.value}</p>
            <p className="mt-1 text-[12px] text-slate-400">{item.label}</p>
            <p className="mt-0.5 text-[10px] text-slate-600">{item.hint}</p>
          </div>
        ))}
      </div>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="Your investors, from CRM to meeting">
        <div className="mb-4 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-white">Your investors, from CRM to meeting</h2>
          <p className="text-[11px] text-slate-500">Each step&apos;s number comes from a connected system</p>
        </div>
        <ol className="grid gap-2 sm:grid-cols-4">
          {FUNNEL_STEPS.map((step) => (
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
              {step.actOn && <p className="mt-2 text-[11px] font-medium text-cyan-300">Act on this step</p>}
            </li>
          ))}
        </ol>
      </section>

      <section className={cn("flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5", CARD)}>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-400">Recommendation</p>
          <h2 className="mt-1 text-[15px] font-semibold text-white">Referral reachout from Lombe House intent</h2>
          <p className="mt-1 max-w-[52ch] text-[13px] text-slate-400">
            1 of 9 labelled reachouts still needs a person. Nothing will be sent automatically.
          </p>
        </div>
        <Link
          href="/studio/intelligence?block=investors&worker=intent-intelligence&pane=outcomes&detail=o-referral&sheet=claude"
          className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-indigo-500 px-4 text-sm font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
        >
          <Sparkles className="size-4" /> Simulate in Claude
        </Link>
      </section>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="How this block works">
        <h2 className="text-sm font-semibold text-white">How this block works</h2>
        <p className="mt-1 text-[13px] text-slate-400">Connected systems → agents → knowledge → where it lands.</p>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-[12px]">
          {["Investor app", "Knowledge library", "Grounded chat"].map((label) => (
            <span key={label} className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-slate-300">
              {label}
            </span>
          ))}
          <ArrowRight className="size-3.5 text-slate-600" />
          <span className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1.5 text-cyan-200">Agents</span>
          <ArrowRight className="size-3.5 text-slate-600" />
          <span className="rounded-lg border border-violet-500/30 bg-violet-500/10 px-2.5 py-1.5 text-violet-200">Knowledge</span>
          <ArrowRight className="size-3.5 text-slate-600" />
          <span className="rounded-lg border border-white/10 px-2.5 py-1.5 text-slate-400">Company record · CRM (planned)</span>
        </div>
      </section>

      <section aria-label="Agents in this block">
        <h2 className="mb-3 text-sm font-semibold text-white">Agents in this block</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {BLOCK_AGENTS.map((agent) => (
            <article key={agent.id} className={cn("p-4", CARD)}>
              <div className="flex items-start gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-500/15 text-indigo-300">
                  <Network className="size-4" />
                </span>
                <div className="min-w-0">
                  <h3 className="truncate text-[14px] font-semibold text-white">{agent.name}</h3>
                  <p className="text-[12px] text-slate-400">{agent.role}</p>
                </div>
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500">Talking</dt>
                  <dd className="mt-0.5 text-lg font-semibold text-white">{agent.talkingNow}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500">Month</dt>
                  <dd className="mt-0.5 text-lg font-semibold text-white">{agent.thisMonth}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500">To CRM</dt>
                  <dd className="mt-0.5 text-lg font-semibold text-white">{agent.toCrm}</dd>
                </div>
              </dl>
              <p className="mt-3 text-[11px] text-slate-500">{agent.connections}</p>
              <p className="mt-1 text-[12px] text-slate-300">{agent.workflow}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="Knowledge being captured">
        <h2 className="text-sm font-semibold text-white">Knowledge being captured</h2>
        <ul className="mt-3 space-y-3">
          {CAPTURED_KNOWLEDGE.map((item) => (
            <li key={item.id} className="flex flex-col gap-2 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-[13.5px] font-medium text-white">{item.title}</p>
                <p className="mt-0.5 text-[12.5px] text-slate-400">{item.evidence}</p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-lg border border-white/10 px-3 py-1.5 text-[12px] text-slate-300 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                >
                  Make it a rule
                </button>
                <Link
                  href="/studio/intelligence?tab=channels&surface=claude"
                  className="rounded-lg bg-indigo-500/90 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                >
                  Simulate in Claude
                </Link>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className={cn("grid gap-3 p-4 sm:grid-cols-3 sm:p-5", CARD)} aria-label="Summary">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">Risk</p>
          <p className="mt-1 text-[13px] text-slate-300">Acting on intent without a person still blocked — walls stay on.</p>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Gap</p>
          <p className="mt-1 text-[13px] text-slate-300">Selling-up patterns are not in this block yet.</p>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-300">Next step</p>
          <p className="mt-1 text-[13px] text-slate-300">Decide the Lombe House referral reachout — approve, hold, or defer.</p>
        </div>
      </section>
    </div>
  );
}
