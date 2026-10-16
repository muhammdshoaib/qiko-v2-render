"use client";

import { Ban } from "lucide-react";
import { WORKERS, type WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { BLOCKS, LEARNING_LABEL } from "./drilldown-data";
import { EvidenceDrawer } from "./evidence-drawer";
import { GhostButton, IllustrativeMark, PulseCard, PulseChip, PulseHeader, PulsePage, PulseTabs } from "./pulse-chrome";
import { REFERRAL, REFERRAL_ID, conversationStage, statusLabel, statusTone } from "./referral";
import type { AgentPane, PulseNav } from "./route";
import { agentPane, blockForWorker } from "./route";

const PANES: { id: AgentPane; label: string }[] = [
  { id: "conversations", label: "Conversations" },
  { id: "learning", label: "Learning" },
  { id: "outcomes", label: "Insights" },
];

export function AgentView({
  nav,
  workerNames,
  onNav,
  onApprove,
  onHold,
  onApproveReferral,
  onRejectReferral,
  onDeferReferral,
}: {
  nav: PulseNav;
  workerNames?: Partial<Record<WorkerId, string>>;
  onNav: (next: Partial<PulseNav>) => void;
  onApprove?: () => void;
  onHold?: () => void;
  onApproveReferral?: () => void;
  onRejectReferral?: () => void;
  onDeferReferral?: () => void;
}) {
  const workerId = nav.worker ?? "intent-intelligence";
  const worker = WORKERS[workerId];
  const blockId = blockForWorker(workerId);
  const block = BLOCKS[blockId];
  const name = workerNames?.[workerId] ?? worker.name;
  const conversations = block.conversations.filter((item) => item.worker === workerId);
  const learnings = block.learnings.filter((item) => item.worker === workerId);
  const outcomes = block.outcomes.filter((item) => item.worker === workerId);
  const referral = useReferral();
  const pane = agentPane(nav.pane);

  return (
    <PulsePage>
      <PulseHeader
        crumbs={[
          { label: "Pulse", onClick: () => onNav({ block: null, worker: null, detail: null, focus: null }) },
          { label: block.name, onClick: () => onNav({ block: blockId, worker: null, detail: null }) },
          { label: name },
        ]}
        eyebrow={`Worker · ${block.name}`}
        title={name}
        description={`${worker.role}. ${worker.purpose}`}
        actions={
          <>
            <IllustrativeMark kind="connected" />
            <GhostButton onClick={() => onNav({ block: blockId, worker: null, detail: null })}>Back to {block.name}</GhostButton>
          </>
        }
      />

      <PulseCard>
        <p className="font-mono text-[10.5px] tracking-[0.1em] text-slate-500 uppercase">Restrictions</p>
        <ul className="mt-2 flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:gap-x-5">
          {worker.hardWalls.map((item) => (
            <li key={item} className="flex gap-2 text-[13px] text-foreground">
              <Ban className="mt-0.5 size-3.5 shrink-0 text-red-400" />
              {item}
            </li>
          ))}
        </ul>
      </PulseCard>

      {workerId === "intent-intelligence" && (
        <section className="rounded-2xl border border-primary/25 bg-card p-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">Primary insight</p>
              <p className="mt-1 text-[14px] font-semibold text-foreground">{REFERRAL.title}</p>
            </div>
            <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <GhostButton onClick={() => onNav({ pane: "conversations", detail: "c-referral" })}>View evidence</GhostButton>
            <GhostButton onClick={() => onNav({ pane: "outcomes", detail: REFERRAL_ID, sheet: null })}>
              Open insight
            </GhostButton>
          </div>
        </section>
      )}

      <PulseTabs
        label="Worker detail"
        value={pane}
        options={PANES.map((item) => ({
          ...item,
          count: item.id === "conversations" ? conversations.length : item.id === "learning" ? learnings.length : outcomes.length,
        }))}
        onChange={(id) => onNav({ pane: id, detail: null })}
      />

      {pane === "conversations" && (
        <PulseCard title="Recent conversations" hint="What it used, what it captured, where it came from." badge={<IllustrativeMark />}>
          {conversations.length === 0 ? (
            <p className="text-sm text-slate-500">No conversations on this worker yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {conversations.map((row) => (
                <li key={row.id}>
                  <button type="button" onClick={() => onNav({ detail: row.id })} className="flex w-full flex-col py-3 text-left first:pt-0">
                    <span className="flex items-start justify-between gap-3">
                      <span className="text-[13.5px] font-medium text-foreground">{row.who}</span>
                      <PulseChip tone={row.id === "c-referral" ? conversationStage(referral.status).tone : row.stageTone}>
                        {row.id === "c-referral" ? conversationStage(referral.status).stage : row.stage}
                      </PulseChip>
                    </span>
                    <span className="mt-1 text-[12.5px] text-slate-400">{row.learned}</span>
                    <span className="mt-1 font-mono text-[11px] text-slate-500">{row.source} · {row.channel} · {row.last}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </PulseCard>
      )}

      {pane === "learning" && (
        <PulseCard title="What it has learned or recorded" hint="Rules already in force sit beside proposed ones.">
          <ul className="divide-y divide-border">
            {learnings.map((item) => {
              const state = LEARNING_LABEL[item.state];
              return (
                <li key={item.id} className="flex flex-col gap-2 py-3 first:pt-0 sm:flex-row sm:justify-between">
                  <button type="button" onClick={() => onNav({ detail: item.id })} className="text-left">
                    <p className="text-[13.5px] font-medium text-foreground">{item.title}</p>
                    <p className="mt-1 text-[12.5px] text-slate-400">{item.evidence}</p>
                  </button>
                  <PulseChip tone={state.tone}>{state.label}</PulseChip>
                </li>
              );
            })}
          </ul>
        </PulseCard>
      )}

      {pane === "outcomes" && (
        <PulseCard title="Outputs and outcomes" hint="Each row is a recorded result, not a decorative counter.">
          {outcomes.length === 0 ? (
            <p className="text-sm text-slate-500">No outcomes recorded yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {outcomes.map((item) => {
                const live = item.id === REFERRAL_ID;
                const tone = live ? statusTone(referral.status) : item.status === "awaiting" ? "warn" : "good";
                const label = live ? statusLabel(referral.status) : item.status === "awaiting" ? "Awaiting you" : "Recorded";
                return (
                <li key={item.id}>
                  <button type="button" onClick={() => onNav({ detail: item.id })} className="flex w-full flex-col py-3 text-left">
                    <span className="flex items-start justify-between gap-3">
                      <span className="text-[13.5px] font-medium text-foreground">{item.title}</span>
                      <PulseChip tone={tone}>{label}</PulseChip>
                    </span>
                    <span className="mt-1 text-[12.5px] text-slate-400">{item.summary}</span>
                    <span className="mt-1 font-mono text-[11px] text-slate-500">{item.when} · {item.from}</span>
                  </button>
                </li>
                );
              })}
            </ul>
          )}
        </PulseCard>
      )}

      <EvidenceDrawer
        nav={nav}
        onClose={() => onNav({ detail: null, sheet: null })}
        onNav={onNav}
        onApprove={onApprove}
        onHold={onHold}
        onApproveReferral={onApproveReferral}
        onRejectReferral={onRejectReferral}
        onDeferReferral={onDeferReferral}
      />
    </PulsePage>
  );
}
