"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { HonestyBadge } from "./honesty-badge";
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
      description="Filterable sample activity. These events are illustrative until event capture is connected."
    >
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter observability">
        {ACTIVITY_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            onClick={() => setFilter(item.id)}
            className={`rounded-full border px-3 py-1 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 ${
              filter === item.id ? "border-white/25 bg-white/10 text-white" : "border-white/[0.08] text-slate-400"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.length === 0 ? (
        <Empty message="No sample events in this filter." />
      ) : (
        <ul className="divide-y divide-white/[0.05] rounded-2xl border border-white/[0.06]">
          {items.map((card) => (
            <li key={card.id}>
              <button
                type="button"
                onClick={() => onInspect(card.focus)}
                className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
              >
                <div>
                  <p className="text-sm text-white">{card.title}</p>
                  <p className="text-[12px] text-slate-400">CRM Agent · {card.detail}</p>
                </div>
                <HonestyBadge kind="illustrative" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[12px] text-slate-500">{feed.length} events. Prototype playbook runs are labelled illustrative — not live automation.</p>
    </Panel>
  );
}

export function TrainTab() {
  return (
    <Panel
      title="Approved learning"
      description="Suggested rule changes stay disabled until there are real, versioned training events."
    >
      <div className="rounded-2xl border border-dashed border-white/10 p-6">
        <p className="text-sm text-white">No reviewed training events yet.</p>
        <p className="mt-2 text-[13px] text-slate-400">This is a labelled preview, not automatic learning from the CRM Agent.</p>
        <div className="mt-3"><HonestyBadge kind="planned" /></div>
        <button
          type="button"
          disabled
          className="mt-4 rounded-lg border border-white/10 px-3 py-2 text-[13px] text-slate-500"
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
            <li key={row.name} className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-white">{row.name}</p>
                  <p className="mt-1 text-[12px] text-slate-400">Owner {row.owner} · Connected {row.connected}</p>
                  <p className="text-[12px] text-slate-500">{row.sensitivity}</p>
                  <p className="mt-1 text-[12px] text-slate-400">External assistant: {row.assistant}</p>
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

export function ConnectionsTab({ onViewBoundary }: { onViewBoundary: (focus: FocusId) => void }) {
  const cards: { id: FocusId; name: string; actions: string; walkthrough?: string }[] = [
    { id: "crm", name: SYSTEMS.crm.name, actions: "Companies, leads, tasks, invoices" },
    { id: "claude", name: SYSTEMS.claude.name, actions: "Retrieval and approval-controlled actions", walkthrough: "/crm/channels?surface=claude" },
    { id: "slack-sales", name: SYSTEMS["slack-sales"].name, actions: "Ops allowed · money blocked", walkthrough: "/crm/channels?surface=slack&channel=sales" },
    { id: "slack-revenue", name: SYSTEMS["slack-revenue"].name, actions: "Finance for authorised users", walkthrough: "/crm/channels?surface=slack&channel=revenue" },
    { id: "email", name: SYSTEMS.email.name, actions: "Outbound needs confirmation", walkthrough: "/crm/channels?surface=claude" },
  ];
  return (
    <Panel title="Where the worker operates" description="Each connection has a readable boundary. Walkthroughs are simulated integrations until live connectors exist.">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <article key={card.id} className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-white">{card.name}</h3>
              <HonestyBadge kind="illustrative" />
            </div>
            <p className="mt-3 text-[12px] text-slate-300">Permitted: {card.actions}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => onViewBoundary(card.id)}
                className="text-[12px] font-medium text-indigo-300 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
              >
                View boundary
              </button>
              {card.walkthrough && (
                <Link href={card.walkthrough} className="text-[12px] font-medium text-indigo-300 underline-offset-2 hover:underline">
                  Open walkthrough
                </Link>
              )}
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
    ["Worker ownership", "CRM Agent"],
    ["Data visibility", "Labelled prototype samples only"],
  ];
  return (
    <Panel title="Governance overview" description="Understand the controls. Advanced administration stays out of this first-path room.">
      <dl className="divide-y divide-white/[0.05] rounded-2xl border border-white/[0.06]">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[160px_1fr] gap-3 px-4 py-3 text-sm">
            <dt className="text-slate-500">{label}</dt>
            <dd className="text-white">{value}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{title}</h2>
        <p className="mt-1 text-sm text-slate-400">{description}</p>
      </div>
      {children}
    </div>
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 px-6 py-12 text-center text-sm text-slate-400">
      {message}
    </div>
  );
}
