"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { Button, cn } from "@qiko/ui";
import { toast } from "sonner";
import { useCrm } from "@/lib/crm/store";
import { channelRunLabel } from "@/lib/crm/channels";
import { runLabel } from "@/lib/crm/workflows";
import { HonestyBadge } from "./honesty-badge";
import {
  ACTIVITY_FILTERS,
  EDGES,
  MONTHLY_DECISIONS,
  SOURCES,
  filterActivity,
  type ActivityFilter,
  type ActivityItem,
} from "./model";
import { useWorkflowBoard } from "./workflow-board";

function formatStamp(at: string) {
  if (at.includes("T")) {
    return new Date(at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  return at;
}

export function RightRail({
  items,
  capturedCount,
  edgeId,
  activityFilter,
  selectedEventId,
  playing,
  onFilter,
  onSelectEvent,
  onPlay,
  onPause,
  onStep,
}: {
  items: ActivityItem[];
  capturedCount: number;
  edgeId: string | null;
  activityFilter: ActivityFilter;
  selectedEventId: string | null;
  playing: boolean;
  onFilter: (filter: ActivityFilter) => void;
  onSelectEvent: (event: ActivityItem) => void;
  onPlay: () => void;
  onPause: () => void;
  onStep: (direction: -1 | 1) => void;
}) {
  const crm = useCrm();
  const board = useWorkflowBoard();
  const visible = filterActivity(items, activityFilter);
  const edge = board.edgeById(edgeId) ?? EDGES.find((item) => item.id === edgeId);
  const selected = items.find((item) => item.id === selectedEventId) ?? null;
  const maxMonth = Math.max(...MONTHLY_DECISIONS.map((row) => row.value));
  const meeting = crm.workflowRuns.find((run) => run.id === "meeting");
  const email = crm.channelRuns?.find((run) => run.id === "claude-email");
  const channelChecks = crm.channelRuns?.filter((run) => run.status !== "idle") ?? [];

  return (
    <aside className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto">
      <RailCard title="Company record">
        <p className="text-3xl font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{capturedCount}</p>
        <p className="mt-1 text-[12px] text-slate-400">Captured decisions · prototype + sample</p>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
          <div className="rounded-lg border border-white/[0.05] bg-white/[0.02] px-2.5 py-2">
            <dt className="text-slate-500">Recent events</dt>
            <dd className="mt-0.5 text-white">{items.length}</dd>
          </div>
          <div className="rounded-lg border border-white/[0.05] bg-white/[0.02] px-2.5 py-2">
            <dt className="text-slate-500">Knowledge sources</dt>
            <dd className="mt-0.5 text-white">{SOURCES.length}</dd>
          </div>
        </dl>
        <div className="mt-4 flex items-end gap-1.5" aria-label="Monthly captured decisions">
          {MONTHLY_DECISIONS.map((row) => (
            <div key={row.month} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex h-14 w-full items-end rounded-sm bg-white/[0.03]">
                <div
                  className="w-full rounded-sm bg-indigo-400/70"
                  style={{ height: `${Math.max(18, (row.value / maxMonth) * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-slate-500">{row.month}</span>
            </div>
          ))}
        </div>
        <div className="mt-2"><HonestyBadge kind="illustrative" /></div>
      </RailCard>

      <RailCard title="Workflow runs">
        <ul className="space-y-2 text-[12px]">
          {crm.workflowRuns.map((run) => (
            <li key={run.id} className="flex items-center justify-between gap-2">
              <span className="text-slate-300">{runLabel(run.id)}</span>
              <span className="capitalize text-slate-500">{run.status.replaceAll("_", " ")}</span>
            </li>
          ))}
        </ul>
        <Link href="/crm" className="mt-3 inline-block text-[12px] text-indigo-300 hover:underline">Open CRM playbooks</Link>
      </RailCard>

      <RailCard title="Channel surfaces">
        {channelChecks.length === 0 ? (
          <p className="text-[13px] text-slate-400">No Claude or Slack checks yet.</p>
        ) : (
          <ul className="space-y-2 text-[12px]">
            {channelChecks.map((run) => (
              <li key={run.id} className="flex items-center justify-between gap-2">
                <span className="text-slate-300">{channelRunLabel(run.id)}</span>
                <span className="capitalize text-slate-500">{run.status.replaceAll("_", " ")}</span>
              </li>
            ))}
          </ul>
        )}
        <Link href="/crm/channels" className="mt-3 inline-block text-[12px] text-indigo-300 hover:underline">Open walkthroughs</Link>
      </RailCard>

      <RailCard title="Approvals">
        {meeting?.status === "awaiting_approval" ? (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
            <p className="text-[13px] text-white">Harrow Street · Negotiation → Confirmed</p>
            <p className="mt-1 text-[12px] text-slate-400">{meeting.pendingApproval?.reason}</p>
            <Button type="button" size="sm" className="mt-3" onClick={() => toast.message(crm.approveMeetingStage())}>
              Approve stage change
            </Button>
          </div>
        ) : email?.status === "awaiting_approval" ? (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
            <p className="text-[13px] text-white">Albemarle follow-up email</p>
            <p className="mt-1 text-[12px] text-slate-400">Draft waiting. Nothing sends until approved.</p>
            <Button type="button" size="sm" className="mt-3" onClick={() => toast.message(crm.approveClaudeEmail())}>
              Approve send
            </Button>
          </div>
        ) : (
          <p className="text-[13px] text-slate-400">No open approvals.</p>
        )}
      </RailCard>

      <RailCard title="Live activity">
        <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Filter activity">
          {ACTIVITY_FILTERS.map((filter) => (
            <button
              key={filter.id}
              type="button"
              aria-pressed={activityFilter === filter.id}
              onClick={() => onFilter(filter.id)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                activityFilter === filter.id ? "border-white/25 bg-white/10 text-white" : "border-white/[0.08] text-slate-400 hover:text-white",
              )}
            >
              {filter.label}
            </button>
          ))}
        </div>

        {visible.length === 0 ? (
          <p className="rounded-lg border border-dashed border-white/10 px-3 py-6 text-center text-[13px] text-slate-500">
            No events in this filter.
          </p>
        ) : (
          <ul className="space-y-2">
            {visible.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  aria-pressed={selectedEventId === item.id}
                  onClick={() => onSelectEvent(item)}
                  className={cn(
                    "w-full rounded-lg border px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                    selectedEventId === item.id ? "border-cyan-400/30 bg-cyan-400/10" : "border-white/[0.05] bg-white/[0.02] hover:bg-white/[0.04]",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] text-white">{item.title}</p>
                    <span className="text-[11px] text-slate-500">{formatStamp(item.at)}</span>
                  </div>
                  <p className="mt-1 text-[12px] text-slate-400">{item.detail}</p>
                </button>
              </li>
            ))}
          </ul>
        )}

        {selected && (
          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
            <p className="text-[11px] uppercase tracking-wider text-slate-500">Event detail</p>
            <p className="mt-1 text-[13px] text-white">{selected.title}</p>
            <p className="mt-1 text-[12px] text-slate-400">{selected.detail}</p>
            <HonestyBadge kind="illustrative" className="mt-2" />
          </div>
        )}

        {edge && !selected && (
          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
            <p className="text-[11px] uppercase tracking-wider text-slate-500">Selected connection</p>
            <p className="mt-1 text-[13px] font-medium text-white">{edge.label}</p>
            <p className="mt-1 text-[12px] leading-relaxed text-slate-300">{edge.rule}</p>
            <p className="mt-1 text-[12px] text-slate-400">Example: {edge.example}</p>
          </div>
        )}
      </RailCard>

      <RailCard title="History replay">
        <p className="text-[12px] text-slate-400">Replays prototype events, including CRM playbook runs. Not live operations.</p>
        <div className="mt-3 flex items-center gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => onStep(-1)} aria-label="Previous sample event">
            <SkipBack className="size-3.5" />
          </Button>
          {playing ? (
            <Button type="button" size="sm" onClick={onPause} aria-label="Pause replay">
              <Pause className="size-3.5" /> Pause
            </Button>
          ) : (
            <Button type="button" size="sm" onClick={onPlay} aria-label="Play sample replay">
              <Play className="size-3.5" /> Replay
            </Button>
          )}
          <Button type="button" size="sm" variant="outline" onClick={() => onStep(1)} aria-label="Next sample event">
            <SkipForward className="size-3.5" />
          </Button>
        </div>
        <HonestyBadge kind="illustrative" className="mt-3" />
      </RailCard>
    </aside>
  );
}

function RailCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{title}</h3>
      {children}
    </section>
  );
}
