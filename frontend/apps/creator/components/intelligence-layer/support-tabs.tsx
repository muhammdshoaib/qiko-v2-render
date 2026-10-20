"use client";

import { useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { HonestyBadge } from "./honesty-badge";
import { ChannelSettings } from "./channel-surfaces";
import { BLOCK_SYSTEM_CONNECTIONS } from "@/components/knowledge/investors-data";
import {
  ACTIVITY,
  ACTIVITY_FILTERS,
  SOURCES,
  SYSTEMS,
  filterActivity,
  type ActivityFilter,
  type ActivityItem,
  type FocusId,
} from "./model";

export function ObservabilityTab({
  onInspect,
  events,
}: {
  onInspect: (focus: FocusId) => void;
  events?: ActivityItem[];
}) {
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const feed = events ?? ACTIVITY;
  const items = filterActivity(feed, filter);
  return (
    <Panel
      title="What actually happened"
      description="Demonstration Claude and Slack events sit above labelled sample activity. Prototype playbook runs are not live automation."
    >
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter observability">
        {ACTIVITY_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            onClick={() => setFilter(item.id)}
            className={`rounded-full border px-3 py-1 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 ${
              filter === item.id ? "border-border bg-slate-100 text-foreground" : "border-border text-slate-500"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.length === 0 ? (
        <Empty message="No sample events in this filter." />
      ) : (
        <ul className="divide-y divide-border rounded-2xl border border-border">
          {items.map((card) => (
            <li key={card.id}>
              <button
                type="button"
                onClick={() => onInspect(card.focus)}
                className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                <div>
                  <p className="text-sm text-foreground">{card.title}</p>
                  <p className="text-[12px] text-slate-500">{card.detail}</p>
                </div>
                <HonestyBadge kind="illustrative" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[12px] text-slate-500">{feed.length} events. Allowed, blocked, and approved actions from this walkthrough appear first.</p>
    </Panel>
  );
}

export function TrainTab() {
  return (
    <Panel
      title="Approved learning"
      description="Suggested rule changes stay disabled until there are real, versioned training events."
    >
      <div className="rounded-2xl border border-dashed border-border p-6">
        <p className="text-sm text-foreground">No reviewed training events yet.</p>
        <p className="mt-2 text-[13px] text-slate-500">This is a labelled preview, not automatic learning from the workers.</p>
        <div className="mt-3"><HonestyBadge kind="planned" /></div>
        <button
          type="button"
          disabled
          className="mt-4 rounded-lg border border-border px-3 py-2 text-[13px] text-slate-500"
        >
          Suggest rule change
        </button>
      </div>
    </Panel>
  );
}

export function SourcesTab() {
  return (
    <Panel title="What the worker knows" description="Lightweight inventory. Sync times stay empty until sources are connected.">
      {SOURCES.length === 0 ? (
        <Empty message="No knowledge sources in this prototype." />
      ) : (
        <ul className="space-y-2">
          {SOURCES.map((row) => (
            <li key={row.name} className="rounded-2xl border border-slate-200 bg-white shadow-sm p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{row.name}</p>
                  <p className="mt-1 text-[12px] text-slate-500">Owner {row.owner} · Connected {row.connected}</p>
                  <p className="text-[12px] text-slate-500">{row.sensitivity}</p>
                  <p className="mt-1 text-[12px] text-slate-500">External assistant: {row.assistant}</p>
                </div>
                <HonestyBadge kind={row.honesty} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function ConnectionsTab({
  onViewBoundary,
  onOpenChannels,
}: {
  onViewBoundary: (focus: FocusId) => void;
  onOpenChannels?: (surface: "claude" | "slack") => void;
}) {
  const [systemBoundary, setSystemBoundary] = useState<(typeof BLOCK_SYSTEM_CONNECTIONS)[number] | null>(null);
  const cards: { id: FocusId; name: string; actions: string }[] = [
    { id: "properties", name: SYSTEMS.properties.name, actions: "Each advised investor’s portfolio, read to write their insight cards" },
    { id: "investor-app", name: SYSTEMS["investor-app"].name, actions: "Intent signals · no outbound contact" },
    { id: "knowledge", name: SYSTEMS.knowledge.name, actions: "Uploaded sources · grounded retrieval" },
    { id: "chat", name: SYSTEMS.chat.name, actions: "Critic + gate on operator questions" },
  ];
  const surfaces = [
    { id: "claude" as const, name: "Claude", actions: "Ask a worker for a grounded insight, then approve a recommended review." },
    { id: "slack" as const, name: "Slack", actions: "Same workers. Channel and user walls decide what can be said." },
  ];
  return (
    <Panel
      title="Where the worker operates"
      description="Each connection has a readable boundary. Connected systems match Investor Concierge · How this block works. Claude and Slack walkthroughs are simulated until live connectors exist."
    >
      {systemBoundary && (
        <div
          className="mb-4 rounded-2xl border border-indigo-200 bg-indigo-50/40 p-4"
          role="dialog"
          aria-label={`${systemBoundary.name} boundary`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[10px] tracking-[0.12em] text-indigo-600 uppercase">Connected system</p>
              <h3 className="mt-1 text-[16px] font-semibold text-foreground">{systemBoundary.name}</h3>
              <p className="mt-1 text-[13px] text-slate-600">{systemBoundary.purpose}</p>
            </div>
            <button
              type="button"
              onClick={() => setSystemBoundary(null)}
              className="grid size-9 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-white hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              aria-label="Close boundary"
            >
              <X className="size-4" />
            </button>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-[11px] font-semibold tracking-wide text-indigo-600 uppercase">Allowed</p>
              <ul className="mt-1 space-y-1 text-[12px] text-slate-600">
                {systemBoundary.allowed.map((item) => (
                  <li key={item}>· {item}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-semibold tracking-wide text-red-600 uppercase">Hard walls</p>
              <ul className="mt-1 space-y-1 text-[12px] text-slate-600">
                {systemBoundary.blocked.map((item) => (
                  <li key={item}>· {item}</li>
                ))}
              </ul>
            </div>
          </div>
          <HonestyBadge kind="illustrative" className="mt-3" />
        </div>
      )}

      <p className="mb-2 font-mono text-[10px] tracking-[0.12em] text-slate-500 uppercase">Worker surfaces</p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <article key={card.id} className="rounded-2xl border border-slate-200 bg-white shadow-sm p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-foreground">{card.name}</h3>
              <HonestyBadge kind="illustrative" />
            </div>
            <p className="mt-3 text-[12px] text-slate-500">Permitted: {card.actions}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => onViewBoundary(card.id)}
                className="min-h-11 text-[12px] font-medium text-indigo-600 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                View boundary
              </button>
            </div>
          </article>
        ))}
        {surfaces.map((card) => (
          <article key={card.id} className="rounded-2xl border border-slate-200 bg-white shadow-sm p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-foreground">{card.name}</h3>
              <HonestyBadge kind="illustrative" />
            </div>
            <p className="mt-3 text-[12px] text-slate-600">{card.actions}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => onOpenChannels?.(card.id)}
                className="min-h-11 text-[12px] font-medium text-indigo-600 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                Open walkthrough
              </button>
            </div>
          </article>
        ))}
      </div>

      <p className="mb-2 mt-6 font-mono text-[10px] tracking-[0.12em] text-slate-500 uppercase">
        Connected systems · Investor Concierge
      </p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {BLOCK_SYSTEM_CONNECTIONS.map((card) => (
          <article key={card.id} className="rounded-2xl border border-slate-200 bg-white shadow-sm p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-foreground">{card.name}</h3>
              <HonestyBadge kind="illustrative" />
            </div>
            <p className="mt-3 text-[12px] text-slate-500">Permitted: {card.actions}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => setSystemBoundary(card)}
                className="min-h-11 text-[12px] font-medium text-indigo-600 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                View boundary
              </button>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}

export function SettingsTab() {
  const rows = [
    ["Tenant", "Qiko"],
    ["Environment", "Demo / preview"],
    ["Viewer access", "Internal walkthrough only"],
    ["Rules version", "v0 · not enforced in this UI"],
    ["Worker ownership", "Property Insights + Intelligence Worker"],
    ["Data visibility", "Labelled prototype samples only"],
  ];
  return (
    <Panel title="Governance overview" description="Understand the controls. Advanced administration stays out of this first-path room.">
      <dl className="divide-y divide-border rounded-2xl border border-border">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[160px_1fr] gap-3 px-4 py-3 text-sm">
            <dt className="text-slate-500">{label}</dt>
            <dd className="text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="pt-2">
        <ChannelSettings />
      </div>
    </Panel>
  );
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
      </div>
      {children}
    </div>
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border px-6 py-12 text-center text-sm text-slate-500">
      {message}
    </div>
  );
}
