"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, Circle, Clock3, ListTodo } from "lucide-react";
import { cn } from "@qiko/ui";
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

export const STATUS_LABEL: Record<ActionStatus, string> = {
  pending: "To do",
  in_progress: "In progress",
  completed: "Done",
};

export const STATUS_CHIP: Record<ActionStatus, string> = {
  pending: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  in_progress: "bg-indigo-50 text-indigo-800 ring-1 ring-indigo-200",
  completed: "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200",
};

export function createPulseAction(item: PulseInsight): PulseAction {
  return {
    id: `act-${Date.now()}`,
    title: `Follow up · ${item.title}`,
    insightId: item.id,
    investorId: item.investorId,
    status: "pending",
    owner: "You",
    due: "Today",
  };
}

/** Unified row for Pulse + Knowledge shared backlog. */
export type DisplayAction = {
  id: string;
  title: string;
  status: ActionStatus;
  owner: string;
  due: string;
  insightId?: string;
  investorId?: string;
  insightTitle?: string;
  investorName?: string;
  sourceLabel?: string;
  origin: "pulse" | "shared";
};

export function toDisplayAction(action: PulseAction): DisplayAction {
  return {
    id: action.id,
    title: action.title,
    status: action.status,
    owner: action.owner,
    due: action.due,
    insightId: action.insightId,
    investorId: action.investorId,
    origin: "pulse",
  };
}

type WorkspaceProps = {
  className?: string;
  investorId: string;
  insightId: string | null;
  onSelectInvestor: (id: string) => void;
  onSelectInsight: (id: string) => void;
  onCreateAction: (insight: PulseInsight) => void;
};

/** Three-pane CRM: investors → insights → detail + action. */
export function InvestorInsightsWorkspace({
  className,
  investorId,
  insightId,
  onSelectInvestor,
  onSelectInsight,
  onCreateAction,
}: WorkspaceProps) {
  const investor = investorById(investorId) ?? PULSE_INVESTORS[0]!;
  const insights = useMemo(() => insightsForInvestor(investor.id), [investor.id]);
  const insight = insightId ? insightById(insightId) : null;

  return (
    <div className={cn("grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)_minmax(0,1.15fr)]", className)}>
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" aria-label="Investors">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-[15px] font-semibold text-slate-900">Investors</h2>
          <p className="mt-0.5 text-[12px] text-slate-500">Joseph Mews investor app</p>
        </div>
        <ul className="max-h-[460px] overflow-y-auto">
          {PULSE_INVESTORS.map((row) => {
            const on = row.id === investor.id;
            return (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => onSelectInvestor(row.id)}
                  className={cn(
                    "flex w-full items-start gap-3 border-b border-slate-100 px-4 py-3 text-left transition-colors last:border-b-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-300",
                    on ? "bg-indigo-50" : "hover:bg-slate-50",
                  )}
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-indigo-100 text-[11px] font-bold text-indigo-700">
                    {row.initials}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[13.5px] font-semibold text-slate-900">{row.name}</span>
                    <span className="block truncate text-[12px] text-slate-500">{row.segment}</span>
                    <span className="mt-1 block text-[11px] text-slate-400">
                      {row.insightCount} insights · {row.conversations} chats
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" aria-label="Insights">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-[15px] font-semibold text-slate-900">{investor.name}</h2>
          <p className="mt-0.5 text-[12px] text-slate-500">Insights · last active {investor.lastActive}</p>
        </div>
        <ul className="max-h-[460px] divide-y divide-slate-100 overflow-y-auto">
          {insights.length === 0 ? (
            <li className="px-4 py-10 text-center text-sm text-slate-500">No insights for this investor yet.</li>
          ) : (
            insights.map((item) => {
              const on = item.id === insightId;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onSelectInsight(item.id)}
                    className={cn(
                      "w-full px-4 py-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-300",
                      on ? "border-l-2 border-l-indigo-500 bg-slate-50" : "border-l-2 border-l-transparent hover:bg-slate-50/80",
                    )}
                  >
                    <span className="block text-[13.5px] font-semibold text-slate-900">{item.title}</span>
                    <span className="mt-1 block text-[12.5px] leading-relaxed text-slate-500">{item.summary}</span>
                    <span className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                      <span>{item.worker}</span>
                      <span>·</span>
                      <span>{item.when}</span>
                    </span>
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </section>

      <section
        className="flex min-h-[460px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        aria-label="Insight detail"
        id="insight-detail"
      >
        {!insight ? (
          <div className="flex flex-1 items-center justify-center px-6 text-sm text-slate-500">
            Select an insight to see details and take action.
          </div>
        ) : (
          <>
            <div className="border-b border-slate-100 px-5 py-4">
              <p className="text-[11px] font-semibold tracking-[0.08em] text-indigo-600 uppercase">Insight</p>
              <h2 className="mt-1 text-[18px] font-bold tracking-[-0.02em] text-slate-900">{insight.title}</h2>
              <p className="mt-1 text-[12.5px] text-slate-500">
                {insight.worker} · {insight.source} · {insight.when}
              </p>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <p className="text-[14px] leading-relaxed text-slate-700">{insight.detail}</p>
              <div>
                <p className="text-[12px] font-semibold text-slate-900">Supporting context</p>
                <ul className="mt-2 space-y-1.5">
                  {insight.evidence.map((line) => (
                    <li key={line} className="rounded-xl bg-slate-50 px-3 py-2 text-[12.5px] text-slate-600">
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="border-t border-slate-100 px-5 py-4">
              <button
                type="button"
                onClick={() => onCreateAction(insight)}
                className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 text-[14px] font-semibold text-white hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                <ListTodo className="size-4" />
                Add to action list
              </button>
              <p className="mt-2 text-center text-[11px] text-slate-500">
                Human backlog: To do → In progress → Done. Nothing is sent automatically.
              </p>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

/** Uncontrolled wrapper for reuse outside Pulse overview. */
export function InvestorInsightsWorkspaceStandalone({
  className,
  showActionList = true,
}: {
  className?: string;
  showActionList?: boolean;
}) {
  const [investorId, setInvestorId] = useState(PULSE_INVESTORS[0]!.id);
  const [insightId, setInsightId] = useState<string | null>(
    insightsForInvestor(PULSE_INVESTORS[0]!.id)[0]?.id ?? null,
  );
  const [actions, setActions] = useState<PulseAction[]>(INITIAL_PULSE_ACTIONS);
  const [actionFilter, setActionFilter] = useState<ActionStatus | "all">("all");

  const selectInvestor = (id: string) => {
    setInvestorId(id);
    setInsightId(insightsForInvestor(id)[0]?.id ?? null);
  };

  const visibleActions = useMemo(() => {
    const rows = actions.map(toDisplayAction);
    return actionFilter === "all" ? rows : rows.filter((a) => a.status === actionFilter);
  }, [actions, actionFilter]);

  return (
    <div className={cn("space-y-5", className)}>
      <InvestorInsightsWorkspace
        investorId={investorId}
        insightId={insightId}
        onSelectInvestor={selectInvestor}
        onSelectInsight={setInsightId}
        onCreateAction={(item) => setActions((prev) => [createPulseAction(item), ...prev])}
      />
      {showActionList && (
        <WaitingForYou
          actions={visibleActions}
          filter={actionFilter}
          onFilter={setActionFilter}
          onStatus={(id, status) => setActions((prev) => prev.map((a) => (a.id === id ? { ...a, status } : a)))}
          onOpen={(action) => {
            if (action.investorId) selectInvestor(action.investorId);
            if (action.insightId) setInsightId(action.insightId);
          }}
        />
      )}
    </div>
  );
}

export function WaitingForYou({
  actions,
  filter,
  onFilter,
  onStatus,
  onOpen,
}: {
  actions: DisplayAction[];
  filter: ActionStatus | "all";
  onFilter: (next: ActionStatus | "all") => void;
  onStatus: (id: string, status: ActionStatus, origin: DisplayAction["origin"]) => void;
  onOpen: (action: DisplayAction) => void;
}) {
  const pendingCount = actions.filter((a) => a.status === "pending" || a.status === "in_progress").length;

  return (
    <section className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" aria-label="Action list">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-slate-900">Action list</h2>
          <p className="mt-0.5 text-[12.5px] text-slate-500">
            To do → In progress → Done · {pendingCount} open
          </p>
        </div>
        <span className="flex-1" />
        <div className="flex flex-wrap gap-1.5">
          {(["all", "pending", "in_progress", "completed"] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => onFilter(key)}
              className={cn(
                "rounded-full px-3 py-1 text-[12px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                filter === key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
              )}
            >
              {key === "all" ? "All" : STATUS_LABEL[key]}
            </button>
          ))}
        </div>
      </div>
      <ul className="divide-y divide-slate-100">
        {actions.length === 0 ? (
          <li className="px-5 py-10 text-center text-sm text-slate-500">Nothing on the action list yet.</li>
        ) : (
          actions.map((action) => {
            const linkedInsight =
              (action.insightId ? insightById(action.insightId) : null) ??
              (action.insightTitle
                ? PULSE_INSIGHTS.find(
                    (item) =>
                      item.title === action.insightTitle ||
                      action.title.includes(item.title),
                  )
                : null);
            const linkedInvestor =
              (action.investorId ? investorById(action.investorId) : null) ??
              (linkedInsight ? investorById(linkedInsight.investorId) : null);
            const who =
              action.investorName ??
              linkedInvestor?.name ??
              (action.origin === "shared" ? action.sourceLabel ?? "Knowledge" : "Investor");
            const what = action.insightTitle ?? linkedInsight?.title ?? "";
            const openPayload: DisplayAction = {
              ...action,
              insightId: action.insightId ?? linkedInsight?.id,
              investorId: action.investorId ?? linkedInsight?.investorId,
            };
            return (
              <li
                key={action.id}
                className="grid items-center gap-x-3 px-5 py-3.5"
                style={{ gridTemplateColumns: "7.25rem minmax(0,1fr) 6.75rem 5.75rem" }}
              >
                <span
                  className={cn(
                    "inline-flex h-6 w-full items-center justify-center whitespace-nowrap rounded-full px-2 text-[11px] font-medium leading-none",
                    STATUS_CHIP[action.status],
                  )}
                >
                  {STATUS_LABEL[action.status]}
                </span>
                <div className="min-w-0 overflow-hidden">
                  <p className="truncate text-[13.5px] font-semibold text-slate-900">{action.title}</p>
                  <p className="mt-0.5 truncate text-[12px] text-slate-500">
                    {who}
                    {what ? ` · ${what}` : ""}
                    {" · "}
                    {action.owner} · due {action.due}
                  </p>
                </div>
                <div className="flex w-[6.75rem] shrink-0 items-center justify-between gap-1">
                  {(
                    [
                      ["pending", Circle],
                      ["in_progress", Clock3],
                      ["completed", CheckCircle2],
                    ] as const
                  ).map(([status, Icon]) => (
                    <button
                      key={status}
                      type="button"
                      title={STATUS_LABEL[status]}
                      onClick={() => onStatus(action.id, status, action.origin)}
                      className={cn(
                        "inline-flex size-8 shrink-0 items-center justify-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                        action.status === status
                          ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                          : "border-slate-200 text-slate-400 hover:border-slate-300 hover:text-slate-700",
                      )}
                    >
                      <Icon className="size-3.5" />
                    </button>
                  ))}
                </div>
                <div className="flex h-8 w-[5.75rem] shrink-0 items-center justify-start">
                  <button
                    type="button"
                    onClick={() => onOpen(openPayload)}
                    className="whitespace-nowrap text-[12px] font-semibold text-indigo-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                  >
                    Open insight
                  </button>
                </div>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
