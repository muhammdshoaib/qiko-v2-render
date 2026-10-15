"use client";

import { useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import {
  BLOCK_AGENTS,
  BLOCK_SYSTEMS,
  CAPTURED_KNOWLEDGE,
  FUNNEL_STEPS,
  INVESTORS_BLOCK,
} from "./investors-data";

const CARD = "rounded-2xl border border-white/[0.08] bg-[#0b0f18]";

const FEED_CHIP: Record<string, string> = {
  blue: "bg-sky-400/10 text-sky-300",
  warn: "bg-amber-400/10 text-amber-300",
  good: "bg-emerald-400/10 text-emerald-400",
};

function BlockFlowDiagram({
  activeAgent,
  onSelectAgent,
}: {
  activeAgent: string;
  onSelectAgent: (id: string) => void;
}) {
  const systems = BLOCK_SYSTEMS;
  const agents = BLOCK_AGENTS;
  const sy = (i: number) => 28 + i * ((260 - 28) / Math.max(systems.length - 1, 1));
  const agY = agents.map((_, i) => 48 + i * (agents.length === 1 ? 0 : 82));
  if (agents.length === 1) agY[0] = 130;
  const ax = 360;
  const kx = 580;
  const ky = 130;
  const cx = 760;

  return (
    <div className="overflow-x-auto">
      <svg viewBox="0 0 860 280" className="min-w-[760px] w-full" role="img" aria-label="Systems feed this knowledge block">
        <defs>
          <linearGradient id="blockFlowGrad" x1="0" x2="1">
            <stop offset="0" stopColor="#3B82F6" />
            <stop offset="1" stopColor="#8B5CF6" />
          </linearGradient>
        </defs>
        {[
          [70, "CONNECTED SYSTEMS"],
          [ax, "KNOWLEDGE BLOCK"],
          [kx, "KNOWLEDGE"],
          [cx, "LANDS IN"],
        ].map(([x, label]) => (
          <text
            key={String(label)}
            x={Number(x)}
            y={14}
            fill="#64748B"
            fontFamily="ui-monospace, monospace"
            fontSize="9.5"
            textAnchor="middle"
            letterSpacing="1.1"
          >
            {label}
          </text>
        ))}

        {agents.flatMap((agent, gi) =>
          agent.systems.map((sys) => {
            const i = systems.indexOf(sys);
            if (i < 0) return null;
            const y1 = sy(i);
            const y2 = agY[gi];
            const d = `M130 ${y1} C${(130 + ax - 100) / 2} ${y1}, ${(130 + ax - 100) / 2} ${y2}, ${ax - 100} ${y2}`;
            return (
              <g key={`${agent.id}-${sys}`}>
                <path d={d} fill="none" stroke="rgba(148,163,184,0.2)" strokeWidth="1.2" />
                <path d={d} fill="none" stroke="#6366F1" strokeOpacity="0.45" strokeWidth="1.2" strokeDasharray="3 6" className="motion-safe:animate-[dash_1.4s_linear_infinite]" />
              </g>
            );
          }),
        )}

        {agY.map((y) => {
          const d = `M${ax + 100} ${y} C${(ax + 100 + kx - 42) / 2} ${y}, ${(ax + 100 + kx - 42) / 2} ${ky}, ${kx - 42} ${ky}`;
          return (
            <g key={y}>
              <path d={d} fill="none" stroke="rgba(148,163,184,0.2)" strokeWidth="1.2" />
              <path d={d} fill="none" stroke="#A78BFA" strokeOpacity="0.55" strokeWidth="1.2" strokeDasharray="3 6" />
            </g>
          );
        })}

        {(() => {
          const d = `M${kx + 42} ${ky} C${(kx + 42 + cx - 60) / 2} ${ky}, ${(kx + 42 + cx - 60) / 2} ${ky}, ${cx - 60} ${ky}`;
          return (
            <g>
              <path d={d} fill="none" stroke="rgba(148,163,184,0.2)" strokeWidth="1.2" />
              <path d={d} fill="none" stroke="#34D399" strokeOpacity="0.55" strokeWidth="1.2" strokeDasharray="3 6" />
            </g>
          );
        })()}

        {systems.map((name, i) => (
          <g key={name}>
            <rect x="8" y={sy(i) - 11} width="122" height="22" rx="11" fill="#111827" stroke="rgba(255,255,255,0.12)" />
            <text x="69" y={sy(i) + 4} fill="#94A3B8" fontSize="11" textAnchor="middle">{name}</text>
          </g>
        ))}

        {agents.map((agent, gi) => {
          const on = activeAgent === agent.id;
          return (
            <g
              key={agent.id}
              role="button"
              tabIndex={0}
              aria-label={`Open ${agent.name}`}
              className="cursor-pointer"
              onClick={() => onSelectAgent(agent.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectAgent(agent.id);
                }
              }}
            >
              <rect
                x={ax - 100}
                y={agY[gi] - 28}
                width="200"
                height="56"
                rx="14"
                fill={on ? "rgba(99,102,241,0.18)" : "#111827"}
                stroke={on ? "#818CF8" : "rgba(255,255,255,0.12)"}
                strokeWidth={on ? 1.6 : 1.2}
              />
              <rect x={ax - 88} y={agY[gi] - 14} width="28" height="28" rx="8" fill="rgba(99,102,241,0.25)" />
              <text x={ax - 74} y={agY[gi] + 4} fill="#A5B4FC" fontSize="11" fontWeight="800" textAnchor="middle">{agent.initials}</text>
              <text x={ax - 50} y={agY[gi] - 2} fill="#F8FAFC" fontSize="12.5" fontWeight="700">{agent.name}</text>
              <text x={ax - 50} y={agY[gi] + 14} fill="#64748B" fontSize="10.5">
                {agent.talkingNow} talking now · {agent.learned} learned
              </text>
              <circle cx={ax + 86} cy={agY[gi] - 14} r="3.5" fill={agent.status === "Learning" ? "#34D399" : "#FBBF24"} />
            </g>
          );
        })}

        <circle cx={kx} cy={ky} r="52" fill="rgba(99,102,241,0.12)" />
        <circle cx={kx} cy={ky} r="40" fill="#0B0F18" stroke="url(#blockFlowGrad)" strokeWidth="3" />
        <text x={kx} y={ky - 2} fill="#F8FAFC" fontSize="14" fontWeight="800" textAnchor="middle">{INVESTORS_BLOCK.valueThisMonth}</text>
        <text x={kx} y={ky + 14} fill="#64748B" fontSize="9.5" textAnchor="middle" fontFamily="ui-monospace, monospace">
          11 HRS SAVED
        </text>

        <rect x={cx - 60} y={ky - 28} width="120" height="56" rx="14" fill="#111827" stroke="rgba(255,255,255,0.12)" />
        <text x={cx} y={ky - 4} fill="#F8FAFC" fontSize="12.5" fontWeight="700" textAnchor="middle">HubSpot</text>
        <text x={cx} y={ky + 14} fill="#34D399" fontSize="11" fontWeight="600" textAnchor="middle">29 deals · £4.1m</text>
      </svg>
      <style>{`@keyframes dash{to{stroke-dashoffset:-20}}`}</style>
    </div>
  );
}

export function InvestorsOverview() {
  const [activeAgent, setActiveAgent] = useState(BLOCK_AGENTS[0]?.id ?? "concierge");

  const openAgent = (id: string) => {
    setActiveAgent(id);
    const agent = BLOCK_AGENTS.find((a) => a.id === id);
    toast.message(`${agent?.name ?? "Agent"} detail opens in the next drill-down. Investors Overview is wired for the demo.`);
  };

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
          href="/studio/intelligence?tab=channels&surface=claude"
          className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-indigo-500 px-4 text-sm font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
        >
          <Sparkles className="size-4" /> Simulate in Claude
        </Link>
      </section>

      {/* 5. How this block works */}
      <section className={cn("overflow-hidden", CARD)} aria-label="How this block works">
        <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.06] px-4 py-3 sm:px-5">
          <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
            How this block works
          </h2>
          <span className="text-[12.5px] text-slate-500">Click an agent</span>
          <span className="flex-1" />
          <span className="inline-flex items-center gap-1.5 rounded-md bg-white/[0.06] px-2 py-1 font-mono text-[10px] tracking-[0.08em] text-slate-400">
            <i className="size-[7px] rounded-full bg-emerald-400" />
            LIVE
          </span>
        </div>
        <div className="px-2 pb-2 pt-1 sm:px-3">
          <BlockFlowDiagram activeAgent={activeAgent} onSelectAgent={openAgent} />
        </div>
      </section>

      <section className={cn("p-4 sm:p-5", CARD)} aria-label="Knowledge being captured">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
            Knowledge being captured
          </h2>
          <span className="text-[12.5px] text-slate-500">Latest first</span>
        </div>
        <ul className="divide-y divide-white/[0.06]">
          {CAPTURED_KNOWLEDGE.map((item) => (
            <li key={item.id} className="grid grid-cols-[32px_minmax(0,1fr)_auto] gap-3 py-3 first:pt-0 last:pb-0 sm:items-center">
              <span className="grid size-8 place-items-center rounded-full bg-indigo-500/15 font-mono text-[10px] font-medium text-indigo-300">
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
              <div className="col-span-2 flex flex-wrap justify-end gap-2 sm:col-span-1">
                {item.primaryAction === "in_use" ? (
                  <span className="rounded-md bg-white/[0.08] px-2 py-1 font-mono text-[10px] tracking-wide text-slate-300 uppercase">
                    In use
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => toast.message("Rule approval is recorded for the demo. No production policy changed.")}
                      className="rounded-lg border border-white/15 px-3 py-1.5 text-[12px] font-medium text-slate-200 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                    >
                      Make it a rule
                    </button>
                    <Link
                      href="/studio/intelligence?tab=channels&surface=claude"
                      className="rounded-lg bg-indigo-500 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                    >
                      Simulate in Claude
                    </Link>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
