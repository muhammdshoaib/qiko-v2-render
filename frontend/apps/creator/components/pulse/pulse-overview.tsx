"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Play, Sparkles } from "lucide-react";
import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import type { ShowcaseWorker } from "@/lib/studio/showcase";
import { toast } from "sonner";
import { LIVE_CAPTURES } from "./live-captures";
import { PulseMap } from "./pulse-map";
import { GhostButton, PulseChip } from "./pulse-chrome";
import { REFERRAL, isDecided } from "./referral";
import type { PulseNav } from "./route";

const VALUE = {
  month: "£42.6k",
  vsAug: "18%",
  hours: "186",
  decisions: "382",
  patterns: "14",
  rules: "3",
  people: "1.2",
};

const KNOWLEDGE_BLOCKS = [
  { id: "investors" as const, name: "Investors", agents: 3, hours: 29, value: "£18.4k", status: "Growing" as const, color: "bg-indigo-400", bar: "w-[100%]" },
  { id: "properties" as const, name: "Properties", agents: 1, hours: 18, value: "£12.1k", status: "Established" as const, color: "bg-cyan-400", bar: "w-[66%]" },
];

const WAITING = [
  {
    tone: "warn" as const,
    chip: "Approve a rule",
    title: 'Ask "is this cash?" early in investor chats',
    detail: "Investor Concierge · 29 cases",
    action: "Review",
    go: { block: "investors" as const, worker: "intent-intelligence" as const, pane: "overview" as const },
  },
  {
    tone: "bad" as const,
    chip: "Risk",
    title: "64% of Gulf investor relationships sit with Sarah K.",
    detail: "If she leaves, this knowledge leaves with her",
    action: "Spread it",
    soon: "Spread relationship",
  },
  {
    tone: "blue" as const,
    chip: "Connect",
    title: "Adviser WhatsApps are a dark zone",
    detail: "Personal chats hold deals we cannot see",
    action: "Connect",
    soon: "Connections",
  },
];

const OUTCOMES = [
  {
    id: "o1",
    title: "Referral programme simulation",
    meta: "Investors · Today 11:20 · Claude",
    status: "Run",
    tone: "good" as const,
  },
  {
    id: "o2",
    title: 'Ask "is this cash?" early',
    meta: "Investors · Suggested today · Investor Concierge",
    status: "Ready to run",
    tone: "blue" as const,
  },
  {
    id: "o3",
    title: "Spread Gulf relationships across the team",
    meta: "Investors · Ready in about 2 weeks · Pulse",
    status: "Forming",
    tone: "" as const,
  },
];

export function PulseOverview({
  workers,
  focus,
  onFocus,
  onHighlight,
  onNav,
  embedded = false,
  askBrain,
}: {
  workers: ShowcaseWorker[];
  focus: FocusId | null;
  onFocus: (id: FocusId | null) => void;
  onHighlight?: (id: FocusId | null) => void;
  onNav: (next: Partial<PulseNav>) => void;
  embedded?: boolean;
  askBrain?: ReactNode;
}) {
  const [open, setOpen] = useState<FocusId | null>(focus);
  const [tick, setTick] = useState(0);
  const referral = useReferral();
  const decided = isDecided(referral.status);
  const workerNames = Object.fromEntries(workers.map((worker) => [worker.slug, worker.name])) as Partial<Record<WorkerId, string>>;
  const highlightOrigin = onHighlight ?? onFocus;
  const captures = LIVE_CAPTURES.slice(tick % LIVE_CAPTURES.length).concat(LIVE_CAPTURES.slice(0, tick % LIVE_CAPTURES.length)).slice(0, 5);

  useEffect(() => {
    setOpen(focus);
  }, [focus]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 4200);
    return () => window.clearInterval(id);
  }, []);

  const highlight = (id: FocusId | null) => {
    setOpen(id);
    highlightOrigin(id);
  };

  const openNode = (id: FocusId) => {
    setOpen(id);
    onFocus(id);
  };

  const soon = (label: string) => {
    toast.message(`${label} opens the same way. Investors is wired up in this prototype.`);
  };

  return (
    <div className="min-h-full bg-background text-foreground">
      <div className={`mx-auto flex w-full max-w-[1400px] flex-col gap-[22px] px-4 sm:px-6 lg:px-8 ${embedded ? "py-4" : "py-6 sm:py-8"}`}>
        {(embedded || askBrain) && (
          <div className="flex justify-end">{askBrain}</div>
        )}

        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-[26px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
              Pulse
            </h1>
            <p className="mt-1 text-[13.5px] text-slate-400">
              Joseph Mews · September · your company brain, live
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <GhostButton onClick={() => soon("Monthly letter")}>Monthly letter</GhostButton>
            <button
              type="button"
              onClick={() => soon("Play the year")}
              className="inline-flex min-h-[38px] items-center gap-2 rounded-[10px] border border-white bg-white px-4 text-[13.5px] font-semibold text-[#05070d] hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
            >
              <Play className="size-3.5 fill-current" />
              Play the year
            </button>
          </div>
        </header>

        <div className="grid items-stretch gap-3.5 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <section className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-card px-6 py-5">
            <span className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-blue-500 to-violet-500" aria-hidden />
            <p className="font-mono text-[11px] tracking-[0.14em] text-violet-400 uppercase">Value from knowledge used this month</p>
            <button
              type="button"
              onClick={() => highlight("record")}
              className="mt-2 block text-left text-[46px] font-extrabold leading-[1.05] tracking-[-0.03em] text-foreground hover:text-indigo-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
              style={{ fontFamily: "var(--font-display)" }}
              title="See how this is worked out"
            >
              {VALUE.month}
            </button>
            <p className="mt-1.5 text-[13.5px] text-slate-400">
              <span className="font-mono text-[10.5px] font-medium text-emerald-400">↗ +{VALUE.vsAug}</span>
              {" "}vs August · {VALUE.hours} expert hours saved ·{" "}
              <button type="button" className="font-semibold text-indigo-300 hover:underline" onClick={() => highlight("record")}>
                How is this worked out?
              </button>
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {[
                [VALUE.decisions, "Decisions captured"],
                [VALUE.patterns, "Patterns learned"],
                [VALUE.rules, "Became company rules"],
                [VALUE.people, "People's worth of time"],
              ].map(([value, label]) => (
                <div key={label} className="rounded-xl bg-white/[0.04] px-3 py-2.5">
                  <b className="block text-[22px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>{value}</b>
                  <span className="text-[12px] text-slate-500">{label}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="flex h-full flex-col rounded-2xl border border-indigo-400/25 bg-gradient-to-br from-indigo-500/15 via-card to-card px-6 py-5">
            <p className="font-mono text-[11px] tracking-[0.14em] text-violet-400 uppercase">Today&apos;s best next move</p>
            <h2 className="mt-2.5 text-[19px] font-extrabold leading-snug tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
              Referrals close in half the time. Worth a referral programme?
            </h2>
            <p className="mt-2 text-[12.5px] text-slate-400">
              Referred investors close in 38 days vs 71, and 64% reach your CRM vs 31%. Ask Claude to simulate a programme on your Pulse data.
            </p>
            <div className="mt-auto flex flex-wrap gap-2 pt-4">
              <button
                type="button"
                onClick={() => {
                  referral.explore();
                  onNav({
                    block: "investors",
                    worker: "intent-intelligence",
                    pane: "outcomes",
                    detail: REFERRAL.id,
                    sheet: "claude",
                  });
                }}
                className="inline-flex min-h-[30px] items-center gap-1.5 rounded-full bg-indigo-500 px-3 text-[12px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
              >
                <Sparkles className="size-3.5" />
                Simulate in Claude
              </button>
              <GhostButton
                className="!min-h-[30px] !rounded-lg !px-3 !text-[12px]"
                onClick={() => onNav({ block: "investors", pane: "outcomes", detail: REFERRAL.id })}
              >
                See last run
              </GhostButton>
            </div>
          </section>

          <div className="min-h-0 h-full lg:min-h-[560px]">
            <PulseMap focus={open} workerNames={workerNames} onSelect={openNode} />
          </div>

          <section className="flex h-full min-h-0 flex-col rounded-2xl border border-white/10 bg-card lg:min-h-[560px]" aria-label="Captured just now">
            <div className="flex shrink-0 items-center gap-2 px-5 pt-4">
              <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                Captured just now
              </h3>
              <span className="flex-1" />
              <span className="inline-flex items-center gap-1.5 rounded-md bg-white/[0.06] px-2 py-1 font-mono text-[10px] tracking-[0.08em] text-slate-400">
                <i className="size-[7px] rounded-full bg-emerald-400" />
                LIVE
              </span>
            </div>
            <ul className="min-h-0 flex-1 divide-y divide-white/[0.06] overflow-y-auto px-5 py-3">
              {captures.map((item, index) => (
                <li key={`${item.text}-${index}`} className="grid grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-3 py-3 first:pt-1">
                  <span className="grid size-8 place-items-center rounded-full bg-indigo-500/15 font-mono text-[10px] font-medium text-indigo-300">
                    {item.initials}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[13.5px] font-semibold text-foreground">{item.text}</p>
                    <p className="truncate text-[12px] text-slate-500">{item.worker} · {item.block === "investor-app" ? "Investors" : "Properties"}</p>
                  </div>
                  <span className="font-mono text-[10.5px] text-slate-500">{index === 0 ? "NOW" : `${index}M`}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <section id="outcomes" aria-label="Outcomes">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <h2 className="text-[17px] font-extrabold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>Outcomes</h2>
            <span className="hidden h-3.5 w-px bg-white/10 sm:block" />
            <span className="text-[12.5px] text-slate-500">Processes run on your knowledge, used in Claude and your tools</span>
            <span className="flex-1" />
            <GhostButton className="!min-h-[30px] !px-3 !text-[12px]" onClick={() => onNav({ block: "investors", pane: "outcomes" })}>
              See all
            </GhostButton>
          </div>
          <div className="overflow-hidden rounded-2xl border border-white/10 bg-card">
            {OUTCOMES.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onNav({ block: "investors", pane: "outcomes", detail: item.id === "o1" ? REFERRAL.id : null })}
                className="grid w-full grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3.5 border-t border-white/[0.06] px-5 py-4 text-left first:border-t-0 hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
              >
                <span className={`grid size-9 place-items-center rounded-[10px] ${item.tone === "good" ? "bg-gradient-to-br from-blue-500 to-violet-500 text-white" : "bg-indigo-500/15 text-indigo-300"}`}>
                  <Sparkles className="size-4" />
                </span>
                <div className="min-w-0">
                  <b className="block truncate font-semibold text-foreground">{item.title}</b>
                  <span className="block truncate text-[12.5px] text-slate-500">{item.meta}</span>
                </div>
                <PulseChip tone={item.tone}>{item.status}</PulseChip>
              </button>
            ))}
          </div>
        </section>

        <div className="grid gap-3.5 lg:grid-cols-2">
          <section aria-label="Waiting for you">
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <h2 className="text-[17px] font-extrabold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>Waiting for you</h2>
              <span className="hidden h-3.5 w-px bg-white/10 sm:block" />
              <span className="text-[12.5px] text-slate-500">Decisions only you can make</span>
            </div>
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-card">
              {WAITING.map((item) => (
                <div key={item.title} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3.5 border-t border-white/[0.06] px-5 py-4 first:border-t-0">
                  <PulseChip tone={item.tone}>{item.chip}</PulseChip>
                  <div className="min-w-0">
                    <div className="font-semibold text-foreground">{item.title}</div>
                    <div className="text-[12.5px] text-slate-500">{item.detail}</div>
                  </div>
                  <GhostButton
                    className="!min-h-[30px] !px-3 !text-[12px]"
                    onClick={() => {
                      if (item.go) onNav(item.go);
                      else if (item.soon) soon(item.soon);
                    }}
                  >
                    {item.action}
                  </GhostButton>
                </div>
              ))}
              {!decided && (
                <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3.5 border-t border-white/[0.06] px-5 py-4">
                  <PulseChip tone="warn">Awaiting a decision</PulseChip>
                  <div className="min-w-0">
                    <div className="font-semibold text-foreground">{REFERRAL.title}</div>
                    <div className="text-[12.5px] text-slate-500">1 of 9 labelled reachouts still needs a person</div>
                  </div>
                  <GhostButton className="!min-h-[30px] !px-3 !text-[12px]" onClick={() => onNav({ block: "investors", pane: "overview" })}>
                    Open
                  </GhostButton>
                </div>
              )}
            </div>
          </section>

          <section aria-label="Knowledge blocks">
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <h2 className="text-[17px] font-extrabold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>Knowledge blocks</h2>
              <span className="hidden h-3.5 w-px bg-white/10 sm:block" />
              <span className="text-[12.5px] text-slate-500">Click to open</span>
            </div>
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-card">
              {KNOWLEDGE_BLOCKS.map((block) => (
                <button
                  key={block.id}
                  type="button"
                  onClick={() => onNav({ block: block.id === "investors" ? "investors" : "properties", worker: null, detail: null })}
                  className="grid w-full grid-cols-[10px_minmax(0,1fr)_auto_auto] items-center gap-x-3.5 gap-y-1 border-t border-white/[0.06] px-5 py-3.5 text-left first:border-t-0 hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                >
                  <i className={`size-2.5 rounded-full ${block.color}`} />
                  <div className="min-w-0">
                    <b className="block font-semibold text-foreground">{block.name}</b>
                    <span className="text-[12.5px] text-slate-500">{block.agents} agents · {block.hours} hrs saved</span>
                  </div>
                  <PulseChip tone={block.status === "Growing" ? "good" : ""}>{block.status}</PulseChip>
                  <span className="min-w-[80px] text-right text-[16px] font-extrabold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{block.value}</span>
                  <span className="col-span-3 col-start-2 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                    <i className={`block h-full ${block.bar} ${block.color}`} />
                  </span>
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
