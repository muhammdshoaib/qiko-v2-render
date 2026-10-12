"use client";

import { useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import { WORKERS, type WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { CompoundingPanel } from "./compounding";
import { BLOCKS, LEARNING_LABEL } from "./drilldown-data";
import { EvidenceDrawer } from "./evidence-drawer";
import { FlowDiagram } from "./flow-diagram";
import { OutcomeRecord } from "./outcome-record";
import { GhostButton, IllustrativeMark, PulseCard, PulseChip, PulseHeader, PulsePage } from "./pulse-chrome";
import { REFERRAL, REFERRAL_ID, conversationStage, statusLabel, statusTone } from "./referral";
import type { PulseNav } from "./route";

export function BlockView({
  nav,
  workerNames,
  onNav,
  onApprove,
  onHold,
  onApproveReferral,
  onRejectReferral,
}: {
  nav: PulseNav;
  workerNames?: Partial<Record<WorkerId, string>>;
  onNav: (next: Partial<PulseNav>) => void;
  onApprove?: () => void;
  onHold?: () => void;
  onApproveReferral?: () => void;
  onRejectReferral?: () => void;
}) {
  const block = BLOCKS[nav.block ?? "investors"];
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";
  const [segment, setSegment] = useState<string | null>(null);
  const captures = useMemo(
    () => (segment ? block.captures.filter((item) => item.id === segment) : block.captures),
    [block.captures, segment],
  );

  const openSnapshot = (opens: (typeof block.snapshot)[number]["opens"]) => {
    if (opens === "worker") onNav({ block: block.id, worker: block.workers[0], detail: null });
    else if (opens === "review") onNav({ detail: block.id === "investors" ? REFERRAL_ID : block.conversations[0]?.id ?? null });
    else if (opens === "sources") document.getElementById("pulse-sources")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else if (opens === "record") document.getElementById("pulse-record")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else document.getElementById("pulse-segments")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <PulsePage>
      <PulseHeader
        crumbs={[
          { label: "Pulse", onClick: () => onNav({ block: null, worker: null, detail: null, focus: null }) },
          { label: block.name },
        ]}
        eyebrow={block.eyebrow}
        title={block.name}
        description={block.summary}
        actions={
          <>
            <IllustrativeMark />
            <GhostButton onClick={() => onNav({ block: null, worker: null, detail: null, focus: null })}>Back to Pulse</GhostButton>
          </>
        }
      />

      {block.id === "investors" && (
        <PulseCard title="Active insight" hint="The end-to-end outcome on this block." badge={<PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>}>
          <p className="text-[13.5px] leading-relaxed text-foreground">{REFERRAL.insight}</p>
          <p className="mt-2 text-[12.5px] text-amber-300/80">{REFERRAL.caution}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <GhostButton onClick={() => onNav({ detail: "c-referral" })}>See evidence</GhostButton>
            <GhostButton onClick={() => onNav({ worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL_ID })}>
              Open Intelligence Worker
            </GhostButton>
            <GhostButton onClick={() => onNav({ worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL_ID })}>
              Open outcome
            </GhostButton>
          </div>
        </PulseCard>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {block.snapshot.map((item) => {
          const value = block.id === "investors" && item.id === "review"
            ? (decided ? "Decided" : "1 recommendation")
            : block.id === "investors" && item.id === "record"
              ? (referral.status === "approved" ? "8 notes" : "7 notes")
              : item.value;
          const hint = block.id === "investors" && item.id === "review"
            ? (decided ? "Referral decision is on the company record." : item.hint)
            : item.hint;
          return (
          <button
            key={item.id}
            type="button"
            onClick={() => openSnapshot(item.opens)}
            className="rounded-2xl border border-white/10 bg-card px-4 py-4 text-left hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
          >
            <span className="block font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">{item.label}</span>
            <span className="mt-1 block text-[20px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
              {value}
            </span>
            <span className="mt-1 block text-[12px] leading-relaxed text-slate-400">{hint}</span>
          </button>
          );
        })}
      </div>

      <PulseCard title="How this block works" hint="Sources feed the worker. The worker writes this knowledge." badge={<IllustrativeMark kind="connected" />}>
        <FlowDiagram
          block={block}
          workerNames={workerNames}
          onSource={(id) => onNav({ detail: id })}
          onWorker={(id) => onNav({ block: block.id, worker: id, detail: null })}
        />
      </PulseCard>

      <div className="grid gap-4 lg:grid-cols-2">
        {block.workers.map((id) => {
          const worker = WORKERS[id];
          return (
            <button
              key={id}
              type="button"
              onClick={() => onNav({ block: block.id, worker: id, detail: null })}
              className="rounded-2xl border border-white/10 bg-card p-5 text-left hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[9.5px] font-medium uppercase tracking-[0.1em] text-primary">Worker</p>
                  <h3 className="mt-1 text-[17px] font-extrabold text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                    {workerNames?.[id] ?? worker.name}
                  </h3>
                  <p className="mt-1 text-[13px] text-slate-400">{worker.role}</p>
                </div>
                <PulseChip tone="good">Active</PulseChip>
              </div>
              <p className="mt-3 text-[13.5px] leading-relaxed text-slate-400">{worker.purpose}</p>
              <p className="mt-3 text-[12.5px] font-semibold text-primary">
                Open worker <ArrowRight className="ml-1 inline size-3.5" />
              </p>
            </button>
          );
        })}
      </div>

      <div id="pulse-segments" className="grid gap-4 lg:grid-cols-2">
        <PulseCard title={block.id === "investors" ? "Meaningful segments" : "Relevant insights"} hint="Click to filter captured knowledge.">
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setSegment(null)}
              className={`flex min-h-11 w-full rounded-xl px-3 text-left text-[13px] ${segment ? "text-slate-500" : "bg-primary/10 font-semibold text-primary"}`}
            >
              <span className="self-center">All captured knowledge</span>
            </button>
            {block.segments.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setSegment(item.id);
                  onNav({ detail: item.id });
                }}
                className={`flex w-full flex-col rounded-xl border px-3 py-3 text-left ${segment === item.id ? "border-primary" : "border-white/10 hover:border-primary/40"}`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[14px] font-semibold text-foreground">{item.name}</span>
                  <span className="font-mono text-[11px] text-slate-500">{item.countLabel}</span>
                </span>
                <span className="mt-1 text-[12.5px] text-slate-400">{item.summary}</span>
                <span className="mt-1 text-[12.5px] text-foreground">{item.signal}</span>
              </button>
            ))}
          </div>
        </PulseCard>

        <PulseCard title="Knowledge being captured" hint={segment ? "Filtered" : "Latest first"} badge={<IllustrativeMark />}>
          {captures.length === 0 ? (
            <p className="text-sm text-slate-500">Nothing in this segment yet.</p>
          ) : (
            <ul className="divide-y divide-white/[0.06]">
              {captures.map((item) => {
                const chip = item.id === "referrals" ? statusLabel(referral.status) : item.chip;
                const tone = item.id === "referrals" ? statusTone(referral.status) : item.tone;
                return (
                <li key={item.title}>
                  <button
                    type="button"
                    onClick={() => item.detail && onNav({ detail: item.id === "referrals" ? REFERRAL_ID : item.detail })}
                    className="flex w-full flex-col py-3 text-left first:pt-0"
                  >
                    <span className="flex items-start justify-between gap-3">
                      <span className="text-[13.5px] font-medium text-foreground">{item.title}</span>
                      <PulseChip tone={tone}>{chip}</PulseChip>
                    </span>
                    <span className="mt-1 text-[12.5px] text-slate-400">{item.evidence}</span>
                    <span className="mt-1 font-mono text-[11px] text-slate-500">{item.at}</span>
                  </button>
                </li>
              );
              })}
            </ul>
          )}
        </PulseCard>
      </div>

      <div id="pulse-sources" className="grid gap-4 lg:grid-cols-2">
        <PulseCard title="Connected sources" hint="What this block can already see.">
          <ul className="space-y-2">
            {block.sources.map((source) => (
              <li key={source.id}>
                <button
                  type="button"
                  onClick={() => onNav({ detail: source.id })}
                  className="flex min-h-11 w-full items-start justify-between gap-3 rounded-xl border border-white/10 px-3 py-3 text-left hover:border-primary/40"
                >
                  <span>
                    <span className="block text-[13.5px] font-semibold text-foreground">{source.name}</span>
                    <span className="block text-[12.5px] text-slate-400">{source.role}</span>
                  </span>
                  <IllustrativeMark kind={source.honesty} />
                </button>
              </li>
            ))}
          </ul>
        </PulseCard>

        <PulseCard id="pulse-record" title="How knowledge accumulates" hint="Illustrative trail — not a live ledger.">
          <ol className="space-y-3">
            {block.accumulation.map((row) => (
              <li key={row.month} className="grid grid-cols-[48px_minmax(0,1fr)] gap-3">
                <span className="font-mono text-[12px] text-slate-500">{row.month}</span>
                <span className="text-[13.5px] text-foreground">
                  {block.id === "investors" && row.month === "Oct" && decided
                    ? referral.status === "approved"
                      ? "Referral recommendation written to company intelligence. No investor was contacted."
                      : "Referral recommendation declined. The insight stays; the action was not written."
                    : row.note}
                </span>
              </li>
            ))}
          </ol>
          <ul className="mt-4 space-y-2 border-t border-white/[0.06] pt-4">
            {block.takeaways.map((line) => (
              <li key={line} className="text-[13.5px] leading-relaxed text-slate-400">{line}</li>
            ))}
          </ul>
        </PulseCard>
      </div>

      <PulseCard title="Recent conversations" hint="Click a row to see what was captured." badge={<IllustrativeMark />}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[13px]">
            <thead>
              <tr className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-slate-500">
                <th className="pb-2 font-medium">Who / what</th>
                <th className="pb-2 font-medium">Source</th>
                <th className="pb-2 font-medium">Stage</th>
                <th className="pb-2 font-medium">Captured</th>
                <th className="pb-2 font-medium">Last</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06]">
              {block.conversations.map((row) => (
                <tr key={row.id}>
                  <td className="py-3">
                    <button type="button" onClick={() => onNav({ detail: row.id })} className="text-left">
                      <span className="block font-semibold text-foreground">{row.who}</span>
                      <span className="block text-[12px] text-slate-500">{row.from}</span>
                    </button>
                  </td>
                  <td className="py-3 text-slate-400">{row.source}</td>
                  <td className="py-3">
                    <PulseChip tone={row.id === "c-referral" ? conversationStage(referral.status).tone : row.stageTone}>
                      {row.id === "c-referral" ? conversationStage(referral.status).stage : row.stage}
                    </PulseChip>
                  </td>
                  <td className="py-3 text-slate-400">{row.learned}</td>
                  <td className="whitespace-nowrap py-3 font-mono text-[11px] text-slate-500">{row.last}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PulseCard>

      {block.id === "investors" && (
        <>
        <PulseCard title="Compounding knowledge" hint="Only the decision you make here is demonstrated learning.">
          <CompoundingPanel />
        </PulseCard>
        <PulseCard title="Outcome on this block" hint="Same record as the Intelligence Worker.">
          <OutcomeRecord onNav={onNav} onApprove={onApproveReferral} onReject={onRejectReferral} />
        </PulseCard>
        <PulseCard title="What it is learning" hint="Approve only the live review. The rest is labelled sample.">
          <ul className="divide-y divide-white/[0.06]">
            {block.learnings.map((item) => {
              const state = item.id === "l-referral"
                ? LEARNING_LABEL[referral.status === "approved" ? "rule" : referral.status === "rejected" ? "observed" : "proposed"]
                : LEARNING_LABEL[item.state];
              return (
                <li key={item.id} className="flex flex-col gap-2 py-3 first:pt-0 sm:flex-row sm:items-start sm:justify-between">
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
        </>
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
