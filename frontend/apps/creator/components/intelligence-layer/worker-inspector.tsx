"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Ban, BookOpen, Eye, Shield, Wrench } from "lucide-react";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "./honesty-badge";
import {
  EDGES,
  RECORD,
  SYSTEM_DETAIL,
  SYSTEMS,
  WORKERS,
  isWorkerId,
  type EdgeId,
  type FocusId,
  type SystemId,
  type WorkerId,
} from "./model";

export function WorkerInspector({
  focus,
  capturedCount,
  onSelectEvidence,
}: {
  focus: FocusId;
  capturedCount?: number;
  onSelectEvidence: (edgeId: EdgeId) => void;
}) {
  if (isWorkerId(focus)) return <AgentDetail id={focus} onSelectEvidence={onSelectEvidence} />;
  if (focus === "record") return <RecordDetail onSelectEvidence={onSelectEvidence} />;
  return <SystemDetail id={focus} onSelectEvidence={onSelectEvidence} />;
}

function AgentDetail({
  id,
  onSelectEvidence,
}: {
  id: WorkerId;
  onSelectEvidence: (edgeId: EdgeId) => void;
}) {
  const worker = WORKERS[id];
  const handoff = EDGES.find((edge) => edge.from === id && edge.to === "record");

  return (
    <InspectorFrame title={worker.name} kicker={worker.role} summary={worker.purpose}>
      <dl className="mb-4 grid grid-cols-2 gap-2 text-[12px]">
        <Metric label="Captured outcomes" value={String(worker.decisions)} />
        <Metric label="Availability" value="Sample" tone="text-amber-300" />
      </dl>

      <InspectorBlock icon={BookOpen} title="Responsibilities" accent="text-slate-600">
        <ul className="space-y-1.5 text-[13px] text-slate-600">
          {worker.responsibilities.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </InspectorBlock>

      <InspectorBlock icon={Eye} title="Can read" accent="text-indigo-600">
        {worker.reads.map((item) => (
          <p key={item.title} className="rounded-lg px-1 py-1.5">
            <span className="block text-[13px] font-medium text-foreground">{item.title}</span>
            <span className="block text-[12px] text-slate-400">{item.detail}</span>
          </p>
        ))}
      </InspectorBlock>
      <InspectorBlock icon={BookOpen} title="Can write" accent="text-emerald-300">
        {worker.writes.map((item) => (
          <p key={item.title} className="rounded-lg px-1 py-1.5">
            <span className="block text-[13px] font-medium text-foreground">{item.title}</span>
            <span className="block text-[12px] text-slate-400">{item.detail}</span>
          </p>
        ))}
      </InspectorBlock>

      <InspectorBlock icon={Wrench} title="Can perform" accent="text-emerald-300">
        <ToolList id={id} mode="allowed" />
      </InspectorBlock>
      <InspectorBlock icon={Shield} title="Needs a person" accent="text-amber-300">
        <ToolList id={id} mode="requires review" />
      </InspectorBlock>
      <InspectorBlock icon={Ban} title="Hard walls" accent="text-red-300">
        <ul className="space-y-1.5 text-[13px] text-slate-700">
          {worker.hardWalls.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </InspectorBlock>

      <InspectorBlock icon={BookOpen} title="Recent actions" accent="text-violet-300">
        <ul className="space-y-2">
          {worker.runs.map((row) => (
            <li key={row.id} className="rounded-lg border border-border bg-muted/50 px-3 py-2">
              <p className="text-[12px] text-slate-500">{row.time}</p>
              <p className="mt-1 text-[13px] text-foreground">{row.result}</p>
            </li>
          ))}
        </ul>
        {handoff && (
          <button
            type="button"
            onClick={() => onSelectEvidence(handoff.id)}
            className="mt-2 text-[12px] font-medium text-violet-300 underline-offset-2 hover:underline"
          >
            Show hand-off to company intelligence
          </button>
        )}
        <Link
          href={`/studio/w/${id}`}
          className="mt-3 inline-flex min-h-11 items-center text-[13px] text-indigo-700 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
        >
          Open worker in Studio
        </Link>
      </InspectorBlock>
    </InspectorFrame>
  );
}

function SystemDetail({ id, onSelectEvidence }: { id: SystemId; onSelectEvidence: (edgeId: EdgeId) => void }) {
  const system = SYSTEMS[id];
  const detail = SYSTEM_DETAIL[id];
  const edges = EDGES.filter((edge) => edge.to === id || edge.from === id);
  return (
    <InspectorFrame title={system.name} kicker="Connected system" summary={detail.purpose}>
      {detail.allowed.length > 0 && (
        <InspectorBlock icon={Eye} title="Allowed" accent="text-indigo-600">
          <List items={detail.allowed} />
        </InspectorBlock>
      )}
      {detail.approval.length > 0 && (
        <InspectorBlock icon={Shield} title="Needs sign-off" accent="text-amber-300">
          <List items={detail.approval} />
        </InspectorBlock>
      )}
      {detail.blocked.length > 0 && (
        <InspectorBlock icon={Ban} title="Hard walls" accent="text-red-300">
          <List items={detail.blocked} />
        </InspectorBlock>
      )}
      <InspectorBlock icon={BookOpen} title="Links" accent="text-slate-600">
        <ul className="space-y-1">
          {edges.map((edge) => (
            <li key={edge.id}>
              <button
                type="button"
                onClick={() => onSelectEvidence(edge.id)}
                className="w-full rounded-lg px-1 py-1.5 text-left text-[13px] text-slate-700 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                {edge.label}
              </button>
            </li>
          ))}
        </ul>
      </InspectorBlock>
    </InspectorFrame>
  );
}

function RecordDetail({ onSelectEvidence }: { onSelectEvidence: (edgeId: EdgeId) => void }) {
  return (
    <InspectorFrame title={RECORD.name} kicker="Shared memory" summary={RECORD.purpose}>
      <p className="mb-4 text-[12px] text-slate-400">{RECORD.rings}</p>
      <InspectorBlock icon={BookOpen} title="What gets written" accent="text-violet-300">
        <p className="text-[13px] leading-relaxed text-slate-600">
          Property notes and intent clusters from the two Studio workers accumulate here.
        </p>
        <button
          type="button"
          onClick={() => onSelectEvidence("property-record")}
          className="mt-2 text-[12px] font-medium text-violet-300 underline-offset-2 hover:underline"
        >
          Show property hand-off
        </button>
      </InspectorBlock>
    </InspectorFrame>
  );
}

function InspectorFrame({
  title,
  kicker,
  summary,
  children,
}: {
  title: string;
  kicker: string;
  summary: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby="worker-inspector-title" className="min-h-0">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{kicker}</p>
          <h2 id="worker-inspector-title" className="mt-1 text-base font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>
            {title}
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-slate-400">{summary}</p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>
      {children}
    </section>
  );
}

function InspectorBlock({
  icon: Icon,
  title,
  accent,
  children,
}: {
  icon: typeof Eye;
  title: string;
  accent: string;
  children: ReactNode;
}) {
  return (
    <div className="mb-4 border-t border-border pt-3">
      <p className={cn("mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider", accent)}>
        <Icon className="size-3.5" /> {title}
      </p>
      {children}
    </div>
  );
}

function Metric({ label, value, tone = "text-foreground" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/50 px-3 py-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className={cn("mt-0.5 font-medium", tone)}>{value}</dd>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5 text-[13px] text-slate-600">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function ToolList({ id, mode }: { id: WorkerId; mode: (typeof WORKERS)[WorkerId]["tools"][number]["mode"] }) {
  const tools = WORKERS[id].tools.filter((tool) => tool.mode === mode);
  if (tools.length === 0) return <p className="text-[13px] text-slate-500">None on this worker.</p>;
  const tone = mode === "allowed" ? "border-emerald-200 text-emerald-300" : mode === "requires review" ? "border-amber-200 text-amber-300" : "border-red-500/25 text-red-300";
  return (
    <ul className="space-y-1.5">
      {tools.map((tool) => (
        <li key={tool.name} className="flex items-center justify-between gap-2 text-[12px]">
          <span className="text-slate-700">{tool.name}</span>
          <span className={cn("rounded-full border px-2 py-0.5", tone)}>{tool.mode}</span>
        </li>
      ))}
    </ul>
  );
}
