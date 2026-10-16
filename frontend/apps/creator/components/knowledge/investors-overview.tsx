"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ListTodo, FileSearch } from "lucide-react";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { addSharedPulseAction } from "@/lib/pulse-action-store";
import {
  BLOCK_AGENTS,
  BLOCK_SYSTEMS,
  CAPTURED_KNOWLEDGE,
  FUNNEL_STEPS,
  INVESTORS_BLOCK,
  type OverviewInsight,
} from "./investors-data";

const CARD = "rounded-2xl border border-slate-200 bg-white shadow-sm";

const FEED_CHIP: Record<string, string> = {
  blue: "bg-sky-50 text-sky-700",
  warn: "bg-amber-50 text-amber-700",
  good: "bg-emerald-50 text-emerald-700",
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
  const agent = agents.find((a) => a.id === activeAgent) ?? agents[0]!;
  const n = Math.max(systems.length - 1, 1);
  const sy = (i: number) => 36 + i * ((320 - 36) / n);
  const ky = 178;
  const ax = 300;
  const kx = 520;
  const lx = 700;

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox="0 0 820 360"
        className="min-w-[720px] w-full"
        role="img"
        aria-label="How Investor Concierge flows from connected systems to knowledge and destinations"
      >
        <defs>
          <linearGradient id="blockFlowGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#3B82F6" />
            <stop offset="1" stopColor="#6366F1" />
          </linearGradient>
          <linearGradient id="blockFlowLine" x1="0" x2="1">
            <stop offset="0" stopColor="#93C5FD" stopOpacity="0.45" />
            <stop offset="0.5" stopColor="#6366F1" stopOpacity="0.9" />
            <stop offset="1" stopColor="#3B82F6" stopOpacity="0.55" />
          </linearGradient>
          <filter id="blockFlowSoft" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#6366F1" floodOpacity="0.18" />
          </filter>
        </defs>

        {[
          [78, "CONNECTED SYSTEMS"],
          [ax, "KNOWLEDGE BLOCK"],
          [kx, "KNOWLEDGE"],
          [lx, "LANDS IN"],
        ].map(([x, label]) => (
          <text
            key={String(label)}
            x={Number(x)}
            y={18}
            fill="#64748B"
            fontFamily="ui-monospace, monospace"
            fontSize="9.5"
            textAnchor="middle"
            letterSpacing="1.2"
          >
            {label}
          </text>
        ))}

        {/* Systems → agent */}
        {systems.map((sys, i) => {
          const y1 = sy(i);
          const y2 = ky;
          const d = `M148 ${y1} C${(148 + ax - 108) / 2} ${y1}, ${(148 + ax - 108) / 2} ${y2}, ${ax - 108} ${y2}`;
          return (
            <g key={`line-${sys}`}>
              <path d={d} fill="none" stroke="#E2E8F0" strokeWidth="1.4" />
              <path d={d} fill="none" stroke="url(#blockFlowLine)" className="pulse-flowline pulse-flowline-fast" />
            </g>
          );
        })}

        {systems.map((name, i) => (
          <g key={name}>
            <rect x="10" y={sy(i) - 12} width="138" height="24" rx="12" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="1.2" />
            <text x="79" y={sy(i) + 4} fill="#334155" fontSize="11.5" textAnchor="middle">
              {name}
            </text>
          </g>
        ))}

        {agents.map((row) => {
          const on = activeAgent === row.id;
          return (
            <g
              key={row.id}
              role="button"
              tabIndex={0}
              aria-label={`Select ${row.name}`}
              className="cursor-pointer"
              onClick={() => onSelectAgent(row.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectAgent(row.id);
                }
              }}
            >
              <rect
                x={ax - 108}
                y={ky - 36}
                width="216"
                height="72"
                rx="16"
                fill={on ? "#EEF2FF" : "#FFFFFF"}
                stroke={on ? "#6366F1" : "#C7D2FE"}
                strokeWidth={on ? 2 : 1.5}
                filter="url(#blockFlowSoft)"
              />
              <circle cx={ax + 88} cy={ky - 20} r="4" fill="#22C55E" />
              <rect x={ax - 92} y={ky - 16} width="32" height="32" rx="10" fill="#E0E7FF" />
              <text x={ax - 76} y={ky + 5} fill="#4F46E5" fontSize="12" fontWeight="800" textAnchor="middle">
                {row.initials}
              </text>
              <text x={ax - 52} y={ky - 2} fill="#0F172A" fontSize="13.5" fontWeight="700">
                {row.name}
              </text>
              <text x={ax - 52} y={ky + 16} fill="#64748B" fontSize="11">
                {row.talkingNow} talking now · {row.learned} learned
              </text>
            </g>
          );
        })}

        <circle cx={kx} cy={ky} r="50" fill="rgba(59,130,246,0.08)" />
        <circle
          cx={kx}
          cy={ky}
          r="42"
          fill="#FFFFFF"
          stroke="url(#blockFlowGrad)"
          strokeWidth="2.75"
          filter="url(#blockFlowSoft)"
        />
        <text x={kx} y={ky - 4} fill="#0F172A" fontSize="16" fontWeight="800" textAnchor="middle">
          {agent.knowledgeValue}
        </text>
        <text x={kx} y={ky + 14} fill="#3B82F6" fontSize="9.5" fontWeight="700" textAnchor="middle" letterSpacing="0.6">
          {agent.hoursSaved}
        </text>

        <rect
          x={lx - 78}
          y={ky - 30}
          width="156"
          height="60"
          rx="14"
          fill="#FFFFFF"
          stroke="#E2E8F0"
          strokeWidth="1.4"
          filter="url(#blockFlowSoft)"
        />
        <text x={lx} y={ky - 2} fill="#0F172A" fontSize="14" fontWeight="700" textAnchor="middle">
          {agent.landsIn.name}
        </text>
        <text x={lx} y={ky + 16} fill="#16A34A" fontSize="12" fontWeight="600" textAnchor="middle">
          {agent.landsIn.detail}
        </text>

        {/* Agent → knowledge → lands in — painted last so gaps stay visible */}
        <g aria-hidden>
          {[
            `M${ax + 108} ${ky} L${kx - 44} ${ky}`,
            `M${kx + 44} ${ky} L${lx - 78} ${ky}`,
          ].map((d) => (
            <g key={d}>
              <path d={d} fill="none" stroke="#DBEAFE" strokeWidth="1.4" />
              <path
                d={d}
                fill="none"
                stroke="#6366F1"
                strokeWidth="1.8"
                strokeLinecap="round"
                className="pulse-flowline pulse-flowline-fast"
              />
            </g>
          ))}
        </g>
      </svg>
      <p className="mt-2 px-1 text-[11px] text-slate-500">
        Labelled demo flow for walkthrough. Connected systems and destinations are illustrative — not live integrations.
      </p>
    </div>
  );
}

export function InvestorsOverview() {
  const [activeAgent, setActiveAgent] = useState(BLOCK_AGENTS[0]?.id ?? "concierge");
  const [selectedId, setSelectedId] = useState<string | null>(CAPTURED_KNOWLEDGE[0]?.id ?? null);
  const selected = CAPTURED_KNOWLEDGE.find((i) => i.id === selectedId) ?? null;

  const addAction = (insight: OverviewInsight) => {
    addSharedPulseAction({
      title: `Follow up · ${insight.title}`,
      insightTitle: insight.title,
      source: "Investor Concierge · Overview",
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
            Business snapshot, evidence-backed insights, and items that need a person.
          </p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      {/* 1 · Business snapshot */}
      <section className={cn("p-4 sm:p-5", CARD)} aria-label="Investor journey snapshot">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Investor journey</h2>
            <p className="text-[12px] text-slate-500">Customer base → app-aware → intent → enquiries/meetings</p>
          </div>
        </div>
        <ol className="grid gap-2 sm:grid-cols-4">
          {FUNNEL_STEPS.map((step) => (
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
              {step.actOn && <p className="mt-2 text-[11px] font-medium text-indigo-600">Needs a human decision</p>}
            </li>
          ))}
        </ol>
      </section>

      {/* 2 · Insights list + detail — one unified panel */}
      <section className={cn("overflow-hidden", CARD)} aria-label="Insights">
        <div className="border-b border-slate-100 px-4 py-3 sm:px-5">
          <h2 className="text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
            Insights
          </h2>
          <p className="mt-0.5 text-[12.5px] text-slate-500">
            Observed evidence — not completed outcomes. Select a row to open detail.
          </p>
        </div>
        <div className="grid lg:grid-cols-[minmax(0,1.05fr)_minmax(300px,0.95fr)]">
          <ul className="divide-y divide-slate-100 lg:border-r lg:border-slate-100">
            {CAPTURED_KNOWLEDGE.map((item) => {
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
                    {INVESTORS_BLOCK.role} · {selected.when}
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
                      onClick={() => document.getElementById("insight-evidence")?.scrollIntoView({ behavior: "smooth" })}
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
                  <p id="insight-evidence" className="mt-3 text-[11px] text-slate-500">
                    Actions stay with you. Nothing is sent to the investor automatically.{" "}
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

      {/* 3 · How this block works — same 4-column blue layout, white theme */}
      <section className={cn("overflow-hidden", CARD)} aria-label="How this block works">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
          <h2 className="text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
            How this block works
          </h2>
          <span className="text-[12.5px] text-slate-500">Click an agent</span>
          <span className="flex-1" />
          <HonestyBadge kind="illustrative" />
        </div>
        <div className="bg-[radial-gradient(ellipse_at_50%_40%,rgba(99,102,241,0.06),transparent_60%)] px-2 pb-3 pt-1 sm:px-3">
          <BlockFlowDiagram activeAgent={activeAgent} onSelectAgent={setActiveAgent} />
        </div>
      </section>
    </div>
  );
}
