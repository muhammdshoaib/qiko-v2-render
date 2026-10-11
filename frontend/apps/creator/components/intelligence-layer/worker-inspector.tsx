"use client";

import type { ReactNode } from "react";
import { Ban, BookOpen, Eye, Shield, Wrench } from "lucide-react";
import { cn } from "@qiko/ui";
import { useCrm } from "@/lib/crm/store";
import { HonestyBadge } from "./honesty-badge";
import {
  CRM_AGENT,
  EDGES,
  RECORD,
  SYSTEM_DETAIL,
  SYSTEMS,
  type EdgeId,
  type FocusId,
  type SystemId,
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
  if (focus === "crm-agent") return <AgentDetail capturedCount={capturedCount} onSelectEvidence={onSelectEvidence} />;
  if (focus === "record") return <RecordDetail onSelectEvidence={onSelectEvidence} />;
  return <SystemDetail id={focus} onSelectEvidence={onSelectEvidence} />;
}

function AgentDetail({
  capturedCount,
  onSelectEvidence,
}: {
  capturedCount?: number;
  onSelectEvidence: (edgeId: EdgeId) => void;
}) {
  const crm = useCrm();
  const recent = crm.workflowEvents.slice(0, 3);

  return (
    <InspectorFrame title={CRM_AGENT.name} kicker={CRM_AGENT.role} summary={CRM_AGENT.purpose}>
      <dl className="mb-4 grid grid-cols-2 gap-2 text-[12px]">
        <Metric label="Captured decisions" value={String(capturedCount ?? CRM_AGENT.decisions)} />
        <Metric label="Availability" value="Preview" tone="text-amber-300" />
      </dl>

      <InspectorBlock icon={BookOpen} title="Responsibilities" accent="text-slate-300">
        <ul className="space-y-1.5 text-[13px] text-slate-300">
          {CRM_AGENT.responsibilities.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </InspectorBlock>

      <InspectorBlock icon={Eye} title="Knowledge it can read" accent="text-cyan-300">
        {CRM_AGENT.reads.map((item) => (
          <button
            key={item.title}
            type="button"
            onClick={() => onSelectEvidence(readEdgeFor(item.title))}
            className="w-full rounded-lg px-1 py-1.5 text-left hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
          >
            <p className="text-[13px] font-medium text-white">{item.title}</p>
            <p className="text-[12px] text-slate-400">{item.detail}</p>
          </button>
        ))}
      </InspectorBlock>

      <InspectorBlock icon={Wrench} title="Tools and permitted actions" accent="text-emerald-300">
        <ToolList mode="allowed" />
      </InspectorBlock>

      <InspectorBlock icon={Shield} title="Approval-required" accent="text-amber-300">
        <ToolList mode="requires review" />
      </InspectorBlock>

      <InspectorBlock icon={Ban} title="Hard walls" accent="text-red-300">
        <ul className="space-y-1.5 text-[13px] text-slate-200">
          {CRM_AGENT.hardWalls.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => onSelectEvidence("agent-slack-sales-blocked")}
          className="mt-2 text-[12px] font-medium text-red-300 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50"
        >
          Show blocked path
        </button>
      </InspectorBlock>

      <InspectorBlock icon={BookOpen} title="Recent runs" accent="text-violet-300">
        {recent.length === 0 ? (
          <p className="rounded-lg border border-dashed border-white/10 px-3 py-4 text-[13px] text-slate-500">
            No recorded runs yet. Create the Albemarle follow-up in CRM to write the first events.
          </p>
        ) : (
          <ul className="space-y-2">
            {recent.map((row) => (
              <li key={row.id} className="rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[12px] text-slate-500">
                    {new Date(row.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
                  </p>
                  <HonestyBadge kind="illustrative" />
                </div>
                <p className="mt-1 text-[13px] text-white">{row.title}</p>
                <p className="mt-1 text-[12px] text-slate-400">{row.detail}</p>
              </li>
            ))}
          </ul>
        )}
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
        <InspectorBlock icon={Eye} title="Allowed" accent="text-cyan-300">
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
      <InspectorBlock icon={BookOpen} title="Links" accent="text-slate-300">
        <ul className="space-y-1">
          {edges.map((edge) => (
            <li key={edge.id}>
              <button
                type="button"
                onClick={() => onSelectEvidence(edge.id)}
                className="w-full rounded-lg px-1 py-1.5 text-left text-[13px] text-slate-200 hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
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
    <InspectorFrame title={RECORD.name} kicker="Institutional memory" summary={RECORD.purpose}>
      <p className="mb-4 text-[12px] text-slate-400">{RECORD.rings}</p>
      <InspectorBlock icon={BookOpen} title="What gets written" accent="text-violet-300">
        <p className="text-[13px] leading-relaxed text-slate-300">
          Accepted outcomes from the CRM Agent — tasks created, confirmed follow-ups, and reviewed stage movement — become captured decisions.
        </p>
        <button
          type="button"
          onClick={() => onSelectEvidence("agent-record")}
          className="mt-2 text-[12px] font-medium text-violet-300 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
        >
          Show hand-off link
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
          <h2 id="worker-inspector-title" className="mt-1 text-base font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
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
    <div className="mb-4 border-t border-white/[0.05] pt-3">
      <p className={cn("mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider", accent)}>
        <Icon className="size-3.5" /> {title}
      </p>
      {children}
    </div>
  );
}

function Metric({ label, value, tone = "text-white" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className={cn("mt-0.5 font-medium", tone)}>{value}</dd>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5 text-[13px] text-slate-300">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function ToolList({ mode }: { mode: (typeof CRM_AGENT.tools)[number]["mode"] }) {
  const tools = CRM_AGENT.tools.filter((tool) => tool.mode === mode);
  const tone = mode === "allowed" ? "border-emerald-500/25 text-emerald-300" : mode === "requires review" ? "border-amber-500/25 text-amber-300" : "border-red-500/25 text-red-300";
  return (
    <ul className="space-y-1.5">
      {tools.map((tool) => (
        <li key={tool.name} className="flex items-center justify-between gap-2 text-[12px]">
          <span className="text-slate-200">{tool.name}</span>
          <span className={cn("rounded-full border px-2 py-0.5", tone)}>{tool.mode}</span>
        </li>
      ))}
    </ul>
  );
}

function readEdgeFor(title: string): EdgeId {
  if (title.startsWith("Claude")) return "agent-claude-read";
  if (title.includes("#sales-pipeline")) return "agent-slack-sales-read";
  if (title.includes("#revenue")) return "agent-slack-revenue";
  return "agent-crm-read";
}
