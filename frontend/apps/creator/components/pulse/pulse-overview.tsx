"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import type { ShowcaseWorker } from "@/lib/studio/showcase";
import {
  addSharedPulseAction,
  listSharedPulseActions,
  setSharedPulseActionStatus,
  subscribeSharedPulseActions,
  type SharedActionStatus,
  type SharedPulseAction,
} from "@/lib/pulse-action-store";
import { cn } from "@qiko/ui";
import {
  createPulseAction,
  InvestorInsightsWorkspace,
  WaitingForYou,
  toDisplayAction,
  type DisplayAction,
} from "./investor-insights-workspace";
import {
  INITIAL_PULSE_ACTIONS,
  PULSE_INSIGHTS,
  PULSE_INVESTORS,
  insightById,
  insightsForInvestor,
  investorById,
  type ActionStatus,
  type PulseAction,
  type PulseInsight,
} from "./pulse-insights-data";
import { PulseMap } from "./pulse-map";
import type { PulseNav } from "./route";

const KNOWLEDGE_BLOCKS = [
  {
    id: "investors" as const,
    name: "Investor Concierge",
    role: "Intent Signal Agent",
    worker: "intent-intelligence" as const,
    value: "£18.4k",
    status: "Growing",
    blurb: "Intent signals and reachouts from investor-app activity.",
  },
  {
    id: "properties" as const,
    name: "Portfolio Reporter",
    role: "Portfolio Insights",
    worker: "property-insights" as const,
    value: "£12.1k",
    status: "Established",
    blurb: "Grounded portfolio cards from advised investors’ holdings.",
  },
];

function sharedToDisplay(item: SharedPulseAction): DisplayAction {
  const status: ActionStatus =
    item.status === "todo" ? "pending" : item.status === "done" ? "completed" : "in_progress";
  return {
    id: item.id,
    title: item.title,
    status,
    owner: "You",
    due: "Today",
    insightTitle: item.insightTitle,
    sourceLabel: item.source,
    origin: "shared",
  };
}

function toSharedStatus(status: ActionStatus): SharedActionStatus {
  if (status === "pending") return "todo";
  if (status === "completed") return "done";
  return "in_progress";
}

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
  const [mapFocus, setMapFocus] = useState<FocusId | null>(focus);
  const [investorId, setInvestorId] = useState(PULSE_INVESTORS[0]!.id);
  const [insightId, setInsightId] = useState<string | null>(
    insightsForInvestor(PULSE_INVESTORS[0]!.id)[0]?.id ?? null,
  );
  const [actions, setActions] = useState<PulseAction[]>(INITIAL_PULSE_ACTIONS);
  const [sharedActions, setSharedActions] = useState<SharedPulseAction[]>([]);
  const [actionFilter, setActionFilter] = useState<ActionStatus | "all">("all");

  const workerNames = Object.fromEntries(workers.map((worker) => [worker.slug, worker.name])) as Partial<
    Record<WorkerId, string>
  >;
  const highlightOrigin = onHighlight ?? onFocus;

  useEffect(() => {
    setMapFocus(focus);
  }, [focus]);

  useEffect(() => {
    const sync = () => setSharedActions(listSharedPulseActions());
    sync();
    return subscribeSharedPulseActions(sync);
  }, []);

  const highlightMap = (id: FocusId | null) => {
    setMapFocus(id);
    highlightOrigin(id);
  };

  const openMapNode = (id: FocusId) => {
    setMapFocus(id);
    onFocus(id);
  };

  const allDisplayActions = useMemo(() => {
    const local = actions.map(toDisplayAction);
    const sharedIds = new Set(sharedActions.map((s) => s.title));
    // Prefer shared row when Knowledge already added the same follow-up title.
    const localUnique = local.filter((a) => !sharedIds.has(a.title));
    return [...sharedActions.map(sharedToDisplay), ...localUnique];
  }, [actions, sharedActions]);

  const pendingActions = useMemo(
    () => allDisplayActions.filter((a) => a.status === "pending" || a.status === "in_progress"),
    [allDisplayActions],
  );
  const visibleActions = useMemo(
    () => (actionFilter === "all" ? allDisplayActions : allDisplayActions.filter((a) => a.status === actionFilter)),
    [allDisplayActions, actionFilter],
  );
  const bestMove = useMemo(() => {
    const pending = pendingActions.find((a) => a.insightId);
    if (pending?.insightId) {
      const insight = insightById(pending.insightId);
      if (insight) return insight;
    }
    return PULSE_INSIGHTS.find((i) => i.status === "new") ?? PULSE_INSIGHTS[0]!;
  }, [pendingActions]);
  const bestInvestor = investorById(bestMove.investorId);
  const recentInsights = useMemo(
    () => [...PULSE_INSIGHTS].sort((a, b) => statusRank(a) - statusRank(b)).slice(0, 6),
    [],
  );

  const selectInvestor = (id: string) => {
    setInvestorId(id);
    setInsightId(insightsForInvestor(id)[0]?.id ?? null);
  };

  const openInsight = (next: PulseInsight) => {
    setInvestorId(next.investorId);
    setInsightId(next.id);
    document.getElementById("insights")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const openAction = (action: DisplayAction) => {
    if (action.investorId) setInvestorId(action.investorId);
    if (action.insightId) setInsightId(action.insightId);
    document.getElementById("insights")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const createAction = (item: PulseInsight) => {
    setActions((prev) => [createPulseAction(item), ...prev]);
    addSharedPulseAction({
      title: `Follow up · ${item.title}`,
      insightTitle: item.title,
      source: "Pulse",
    });
  };

  const setActionStatus = (id: string, status: ActionStatus, origin: DisplayAction["origin"]) => {
    if (origin === "shared") {
      setSharedPulseActionStatus(id, toSharedStatus(status));
      return;
    }
    setActions((prev) => prev.map((a) => (a.id === id ? { ...a, status } : a)));
  };

  return (
    <div className="min-h-full bg-slate-50">
      <div
        className={cn(
          "mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 sm:px-6 lg:px-8",
          embedded ? "py-4" : "py-6 sm:py-8",
        )}
      >
        {(embedded || askBrain) && askBrain ? <div className="flex justify-end">{askBrain}</div> : null}

        {/* 1. Header */}
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1
                className="text-[28px] font-bold tracking-[-0.03em] text-slate-900"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Pulse
              </h1>
              <HonestyBadge kind="illustrative" />
            </div>
            <p className="mt-1 max-w-[56ch] text-[14px] text-slate-600">
              Insight → action list → knowledge record. Human-managed follow-ups only.
            </p>
          </div>
          <p className="text-[12.5px] text-slate-500">
            {PULSE_INSIGHTS.length} insights · {pendingActions.length} on action list
          </p>
        </header>

        {/* 2. Value + best next move */}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.9fr)]">
          <section
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
            aria-label="Value from knowledge"
          >
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-mono text-[10px] tracking-[0.14em] text-slate-500 uppercase">
                Value from knowledge used this month
              </p>
              <HonestyBadge kind="illustrative" className="scale-90" />
            </div>
            <div className="mt-2 flex flex-wrap items-end gap-3">
              <p
                className="text-[36px] font-extrabold tracking-[-0.04em] text-slate-900 sm:text-[40px]"
                style={{ fontFamily: "var(--font-display)" }}
              >
                £30.5k
              </p>
            </div>
            <p className="mt-1 text-[13px] text-slate-500">
              Illustrative total across Investor Concierge and Portfolio Reporter — not a live customer result.
            </p>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                [String(PULSE_INSIGHTS.length), "Insights open"],
                [String(pendingActions.length), "Action list"],
                [String(KNOWLEDGE_BLOCKS.length), "Knowledge blocks"],
                [String(PULSE_INVESTORS.length), "Investors active"],
              ].map(([value, label]) => (
                <div key={label} className="rounded-xl bg-slate-50 px-3 py-2.5">
                  <p className="text-[18px] font-bold tracking-[-0.02em] text-slate-900">{value}</p>
                  <p className="mt-0.5 text-[11px] text-slate-500">{label}</p>
                </div>
              ))}
            </div>
          </section>

          <section
            className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
            aria-label="Best next move"
          >
            <p className="font-mono text-[10px] tracking-[0.14em] text-slate-500 uppercase">
              Today&apos;s best next move
            </p>
            <div className="mt-3 flex flex-1 flex-col">
              <div className="flex items-start gap-2">
                <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-600">
                  <Sparkles className="size-4" />
                </span>
                <div className="min-w-0">
                  <h2 className="text-[16px] font-semibold leading-snug text-slate-900">{bestMove.title}</h2>
                  <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{bestMove.summary}</p>
                  <p className="mt-2 text-[12px] text-slate-500">
                    {bestInvestor?.name ?? "Investor"} · {bestMove.worker}
                  </p>
                </div>
              </div>
              <div className="mt-auto flex flex-wrap gap-2 pt-5">
                <button
                  type="button"
                  onClick={() => openInsight(bestMove)}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-indigo-600 px-4 text-[13px] font-semibold text-white hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                >
                  Open insight
                  <ArrowRight className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => createAction(bestMove)}
                  className="inline-flex min-h-10 items-center rounded-xl border border-slate-200 bg-white px-4 text-[13px] font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                >
                  Add to action list
                </button>
              </div>
            </div>
          </section>
        </div>

        {/* 3. Knowledge map + live feed */}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.9fr)]">
          <section
            className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
            aria-label="Knowledge map"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
              <div>
                <h2 className="text-[15px] font-semibold text-slate-900">Knowledge map</h2>
                <p className="text-[12.5px] text-slate-500">
                  Investor Concierge and Portfolio Reporter · click a block to open
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <HonestyBadge kind="illustrative" className="scale-90" />
                <button
                  type="button"
                  onClick={() => highlightMap("record")}
                  className="text-[12px] font-semibold text-indigo-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                >
                  Company intelligence
                </button>
              </div>
            </div>
            <div className="min-h-[420px] bg-white">
              <PulseMap focus={mapFocus} workerNames={workerNames} onSelect={openMapNode} />
            </div>
          </section>

          <section
            className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
            aria-label="Captured just now"
          >
            <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-5 py-3.5">
              <div>
                <h2 className="text-[15px] font-semibold text-slate-900">Captured just now</h2>
                <p className="mt-0.5 text-[12.5px] text-slate-500">Recent insights from knowledge blocks</p>
              </div>
              <HonestyBadge kind="illustrative" className="scale-90" />
            </div>
            <ul className="divide-y divide-slate-100">
              {recentInsights.map((item) => {
                const inv = investorById(item.investorId);
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => openInsight(item)}
                      className="flex w-full items-start gap-3 px-5 py-3.5 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-300"
                    >
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-100 text-[11px] font-bold text-slate-600">
                        {inv?.initials ?? "?"}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13.5px] font-semibold text-slate-900">{item.title}</span>
                        <span className="mt-0.5 block text-[12px] text-slate-500">
                          {inv?.name} · {item.worker}
                        </span>
                      </span>
                      <span className="shrink-0 text-[11px] font-medium text-slate-400">{item.when}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>

        {/* 4. Insights CRM */}
        <section id="insights" aria-label="Insights" className="scroll-mt-4">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2
                className="text-[18px] font-bold tracking-[-0.02em] text-slate-900"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Insights
              </h2>
              <p className="mt-0.5 text-[13px] text-slate-500">
                Investor → insight → evidence. Add a follow-up when you are ready.
              </p>
            </div>
          </div>
          <InvestorInsightsWorkspace
            investorId={investorId}
            insightId={insightId}
            onSelectInvestor={selectInvestor}
            onSelectInsight={setInsightId}
            onCreateAction={createAction}
          />
        </section>

        {/* 5. Action list — full width to align with Insights / Supporting context above */}
        <WaitingForYou
          actions={visibleActions}
          filter={actionFilter}
          onFilter={setActionFilter}
          onStatus={setActionStatus}
          onOpen={openAction}
        />

        {/* 6. Knowledge blocks */}
        {/* <section aria-label="Knowledge blocks" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-3.5">
            <h2 className="text-[15px] font-semibold text-slate-900">Knowledge blocks</h2>
            <p className="mt-0.5 text-[12.5px] text-slate-500">Click to open · one block, one worker</p>
          </div>
          <div className="grid divide-y divide-slate-100 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
            {KNOWLEDGE_BLOCKS.map((block) => (
              <button
                key={block.id}
                type="button"
                onClick={() =>
                  onNav({
                    block: block.id === "investors" ? "investors" : "properties",
                    worker: block.worker,
                    detail: null,
                  })
                }
                className="flex w-full items-start justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-300"
              >
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold text-slate-900">{block.name}</p>
                  <p className="mt-0.5 text-[12px] text-indigo-600">{block.role}</p>
                  <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-500">{block.blurb}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-[14px] font-bold text-slate-900">{block.value}</p>
                  <span className="mt-1 inline-flex rounded-md bg-emerald-50 px-2 py-0.5 font-mono text-[10px] font-medium text-emerald-700">
                    {block.status}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section> */}
      </div>
    </div>
  );
}

function statusRank(insight: PulseInsight) {
  if (insight.status === "new") return 0;
  if (insight.status === "reviewed") return 1;
  return 2;
}
