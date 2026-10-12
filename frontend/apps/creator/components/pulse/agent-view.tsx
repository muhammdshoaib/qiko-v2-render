"use client";

import { Ban } from "lucide-react";
import { WORKERS, type WorkerId } from "@/components/intelligence-layer/model";
import { SHOWCASE_WORKERS } from "@/lib/studio/showcase";
import { useReferral } from "@/lib/brain/referral-store";
import { BLOCKS, LEARNING_LABEL } from "./drilldown-data";
import { EvidenceDrawer } from "./evidence-drawer";
import { GhostButton, IllustrativeMark, PulseCard, PulseChip, PulseHeader, PulsePage } from "./pulse-chrome";
import { REFERRAL, REFERRAL_ID, conversationStage, statusLabel, statusTone } from "./referral";
import type { AgentPane, PulseNav } from "./route";
import { blockForWorker } from "./route";

const PANES: { id: AgentPane; label: string }[] = [
  { id: "conversations", label: "Conversations" },
  { id: "learning", label: "Learning" },
  { id: "outcomes", label: "Outcomes" },
];

export function AgentView({
  nav,
  workerNames,
  awaiting,
  onNav,
  onApprove,
  onHold,
  onApproveReferral,
  onRejectReferral,
}: {
  nav: PulseNav;
  workerNames?: Partial<Record<WorkerId, string>>;
  awaiting?: boolean;
  onNav: (next: Partial<PulseNav>) => void;
  onApprove?: () => void;
  onHold?: () => void;
  onApproveReferral?: () => void;
  onRejectReferral?: () => void;
}) {
  const workerId = nav.worker ?? "intent-intelligence";
  const worker = WORKERS[workerId];
  const showcase = SHOWCASE_WORKERS.find((item) => item.slug === workerId);
  const blockId = blockForWorker(workerId);
  const block = BLOCKS[blockId];
  const name = workerNames?.[workerId] ?? worker.name;
  const conversations = block.conversations.filter((item) => item.worker === workerId);
  const learnings = block.learnings.filter((item) => item.worker === workerId);
  const outcomes = block.outcomes.filter((item) => item.worker === workerId);
  const pending = awaiting && workerId === "intent-intelligence";
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";

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
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          <Fact label="Uses" items={worker.reads.map((item) => item.title)} />
          <Fact label="Writes" items={worker.writes.map((item) => item.title)} />
          <Fact label="Allowed" items={worker.tools.filter((item) => item.mode === "allowed").map((item) => item.name)} />
          <div>
            <p className="font-mono text-[10.5px] tracking-[0.1em] text-slate-500 uppercase">Restrictions</p>
            <ul className="mt-2 space-y-1.5">
              {worker.hardWalls.map((item) => (
                <li key={item} className="flex gap-2 text-[13px] text-foreground">
                  <Ban className="mt-0.5 size-3.5 shrink-0 text-red-400" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </PulseCard>

      {workerId === "intent-intelligence" && (
        <section className="rounded-2xl border border-primary/25 bg-card p-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">Primary outcome</p>
              <p className="mt-1 text-[14px] font-semibold text-foreground">{REFERRAL.title}</p>
            </div>
            <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
          </div>
          <p className="mt-2 text-[13px] leading-relaxed text-slate-400">{REFERRAL.insight}</p>
          <p className="mt-2 text-[12.5px] text-amber-300/80">{REFERRAL.caution}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <GhostButton onClick={() => onNav({ pane: "conversations", detail: "c-referral" })}>See evidence</GhostButton>
            <GhostButton
              onClick={() => {
                referral.explore();
                onNav({ pane: "outcomes", detail: REFERRAL_ID, sheet: "claude" });
              }}
            >
              {decided ? "Review in Claude" : "Explore in Claude"}
            </GhostButton>
            <GhostButton onClick={() => onNav({ pane: "outcomes", detail: REFERRAL_ID })}>Open outcome</GhostButton>
          </div>
        </section>
      )}

      {pending && (
        <section className="rounded-2xl border border-amber-400/20 bg-amber-400/10 p-5">
          <p className="font-mono text-[10.5px] tracking-[0.1em] text-amber-400 uppercase">Also awaiting</p>
          <p className="mt-1 text-[14px] font-semibold text-foreground">Lombay House cluster needs a human look.</p>
          <p className="mt-1 text-[13px] text-slate-400">A second existing path. Approving writes the cluster to company intelligence. Nothing is sent outbound.</p>
          {onApprove && onHold && (
            <div className="mt-3 flex flex-wrap gap-2">
              <GhostButton onClick={onApprove}>Approve review</GhostButton>
              <GhostButton onClick={onHold}>Hold</GhostButton>
            </div>
          )}
        </section>
      )}

      <div className="flex flex-wrap gap-1 rounded-xl bg-white/[0.04] p-1" role="tablist" aria-label="Worker detail">
        {PANES.map((pane) => {
          const count = pane.id === "conversations" ? conversations.length : pane.id === "learning" ? learnings.length : outcomes.length;
          const on = nav.pane === pane.id;
          return (
            <button
              key={pane.id}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => onNav({ pane: pane.id, detail: null })}
              className={`inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-[12px] font-medium ${on ? "bg-white text-[#05070d]" : "text-slate-400 hover:text-white"}`}
            >
              {pane.label}
              <span className="font-mono text-[10px] text-slate-500">{count}</span>
            </button>
          );
        })}
      </div>

      {nav.pane === "conversations" && (
        <PulseCard title="Recent conversations" hint="What it used, what it captured, where it came from." badge={<IllustrativeMark />}>
          {conversations.length === 0 ? (
            <p className="text-sm text-slate-500">No conversations on this worker yet.</p>
          ) : (
            <ul className="divide-y divide-white/[0.06]">
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

      {nav.pane === "learning" && (
        <PulseCard title="What it has learned or recorded" hint="Rules already in force sit beside proposed ones.">
          <ul className="divide-y divide-white/[0.06]">
            {learnings.map((item) => {
              const state = item.id === "l-referral"
                ? LEARNING_LABEL[referral.status === "approved" ? "rule" : referral.status === "rejected" ? "observed" : "proposed"]
                : LEARNING_LABEL[item.state];
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

      {nav.pane === "outcomes" && (
        <PulseCard title="Outputs and outcomes" hint="Each row is a recorded result, not a decorative counter.">
          {outcomes.length === 0 ? (
            <p className="text-sm text-slate-500">No outcomes recorded yet.</p>
          ) : (
            <ul className="divide-y divide-white/[0.06]">
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

      {showcase && (
        <PulseCard title="Connections" hint="Same sources as the worker profile — not a second CRM.">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="font-mono text-[10.5px] tracking-[0.1em] text-slate-500 uppercase">Reads</p>
              <ul className="mt-2 space-y-2">
                {showcase.sources.map((item) => (
                  <li key={item.name}>
                    <p className="text-[13.5px] font-medium text-foreground">{item.name}</p>
                    <p className="text-[12.5px] text-slate-400">{item.detail}</p>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-mono text-[10.5px] tracking-[0.1em] text-slate-500 uppercase">Permissions</p>
              <ul className="mt-2 space-y-2">
                {showcase.permissions.map((item) => (
                  <li key={item.name} className="flex items-center justify-between gap-3 text-[13px]">
                    <span className="text-foreground">{item.name}</span>
                    <PulseChip tone={item.mode === "blocked" ? "bad" : item.mode === "requires review" ? "warn" : "good"}>
                      {item.mode}
                    </PulseChip>
                  </li>
                ))}
              </ul>
            </div>
          </div>
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
      />
    </PulsePage>
  );
}

function Fact({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="font-mono text-[10.5px] tracking-[0.1em] text-slate-500 uppercase">{label}</p>
      <ul className="mt-2 space-y-1.5 text-[13px] text-foreground">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
