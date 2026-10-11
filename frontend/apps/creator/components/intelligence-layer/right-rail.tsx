"use client";

import type { ReactNode } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { Button, cn } from "@qiko/ui";
import { HonestyBadge } from "./honesty-badge";
import {
  ACTIVITY_FILTERS,
  EDGES,
  MONTHLY_DECISIONS,
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
  const board = useWorkflowBoard();
  const visible = filterActivity(items, activityFilter);
  const edge = board.edgeById(edgeId) ?? EDGES.find((item) => item.id === edgeId);
  const selected = items.find((item) => item.id === selectedEventId) ?? null;
  const maxMonth = Math.max(...MONTHLY_DECISIONS.map((row) => row.value));

  const waiting = items.filter((item) => item.filter === "approval");
  const blocked = items.filter((item) => item.filter === "blocked");

  return (
    <aside className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto">
      <RailCard title="Record growth">
        <p className="text-3xl font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{capturedCount}</p>
        <p className="mt-1 text-[12px] text-slate-400">Captured outcomes on the company record</p>
        <div className="mt-4 flex items-end gap-1.5" aria-label="Monthly captured outcomes">
          {MONTHLY_DECISIONS.map((row) => (
            <div key={row.month} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex h-14 w-full items-end rounded-sm bg-white/[0.03]">
                <div
                  className="w-full rounded-sm bg-cyan-400/70"
                  style={{ height: `${Math.max(18, (row.value / maxMonth) * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-slate-500">{row.month}</span>
            </div>
          ))}
        </div>
        <div className="mt-2"><HonestyBadge kind="illustrative" /></div>
      </RailCard>

      <RailCard title="Needs a person">
        {waiting.length === 0 ? (
          <p className="text-[13px] text-slate-500">Nothing waiting for review.</p>
        ) : (
          <ul className="space-y-2">
            {waiting.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelectEvent(item)}
                  className="w-full rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                >
                  <p className="text-[13px] text-white">{item.title}</p>
                  <p className="mt-1 text-[12px] text-slate-400">{item.detail}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </RailCard>

      <RailCard title="Blocked">
        {blocked.length === 0 ? (
          <p className="text-[13px] text-slate-500">No blocked actions in this preview.</p>
        ) : (
          <ul className="space-y-2">
            {blocked.map((item) => (
              <li key={item.id} className="rounded-lg border border-red-400/15 bg-red-400/[0.04] px-3 py-2">
                <p className="text-[13px] text-white">{item.title}</p>
                <p className="mt-1 text-[12px] text-slate-400">{item.detail}</p>
              </li>
            ))}
          </ul>
        )}
      </RailCard>

      <RailCard title="Insights and activity">
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
        <p className="text-[12px] text-slate-400">Replays labelled sample outcomes from the two Studio workers.</p>
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
