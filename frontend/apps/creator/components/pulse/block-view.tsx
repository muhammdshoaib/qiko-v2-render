"use client";

import { ArrowRight } from "lucide-react";
import { WORKERS, type WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { CompoundingPanel } from "./compounding";
import { BLOCKS, LEARNING_LABEL, type BlockContent } from "./drilldown-data";
import { EvidenceDrawer } from "./evidence-drawer";
import { GhostButton, IllustrativeMark, PulseCard, PulseChip, PulseHeader, PulsePage, PulseTabs } from "./pulse-chrome";
import { REFERRAL, REFERRAL_EVIDENCE_ID, REFERRAL_ID, conversationStage, statusLabel, statusTone } from "./referral";
import type { BlockPane, PulseNav } from "./route";
import { blockPane } from "./route";

const TABS: { id: BlockPane; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "activity", label: "Activity" },
  { id: "learning", label: "Learning" },
  { id: "outcomes", label: "Outcomes" },
];

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
  const pane = blockPane(nav.pane);
  const decided = referral.status === "approved" || referral.status === "rejected";

  const openSnapshot = (opens: (typeof block.snapshot)[number]["opens"]) => {
    if (opens === "worker") onNav({ block: block.id, worker: block.workers[0], detail: null });
    else if (opens === "review") onNav({ pane: "outcomes", detail: block.id === "investors" ? REFERRAL_ID : block.outcomes[0]?.id ?? null });
    else if (opens === "record") onNav({ pane: "learning", detail: null });
    else if (opens === "sources") onNav({ pane: "overview", detail: null });
    else onNav({ pane: "overview", detail: null });
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

      <PulseTabs
        label={`${block.name} sections`}
        value={pane}
        options={TABS.map((tab) => ({
          ...tab,
          count: tab.id === "activity"
            ? block.conversations.length
            : tab.id === "learning"
              ? block.learnings.length
              : tab.id === "outcomes"
                ? block.outcomes.length
                : undefined,
        }))}
        onChange={(id) => onNav({ pane: id, detail: null })}
      />

      {pane === "overview" && (
        <Overview
          block={block}
          workerNames={workerNames}
          reviewValue={block.id === "investors" ? (decided ? "Decided" : "1 awaiting") : undefined}
          onNav={onNav}
          onSnapshot={openSnapshot}
        />
      )}
      {pane === "activity" && <Activity block={block} onNav={onNav} />}
      {pane === "learning" && <Learning block={block} onNav={onNav} />}
      {pane === "outcomes" && <Outcomes block={block} onNav={onNav} />}

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

function Overview({
  block,
  workerNames,
  reviewValue,
  onNav,
  onSnapshot,
}: {
  block: BlockContent;
  workerNames?: Partial<Record<WorkerId, string>>;
  reviewValue?: string;
  onNav: (next: Partial<PulseNav>) => void;
  onSnapshot: (opens: BlockContent["snapshot"][number]["opens"]) => void;
}) {
  const referral = useReferral();

  return (
    <>
      {block.id === "investors" ? (
        <section className="rounded-2xl border border-primary/25 bg-card p-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">Highlighted insight</p>
              <h2 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                {REFERRAL.title}
              </h2>
            </div>
            <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
          </div>
          <p className="mt-2 max-w-[68ch] text-[13.5px] leading-relaxed text-foreground">{REFERRAL.insight}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <GhostButton onClick={() => onNav({ pane: "activity", detail: REFERRAL_EVIDENCE_ID })}>See evidence</GhostButton>
            <GhostButton onClick={() => onNav({ block: "investors", worker: "intent-intelligence", pane: "conversations", detail: null })}>
              Open Intelligence Worker
            </GhostButton>
            <GhostButton onClick={() => onNav({ pane: "outcomes", detail: REFERRAL_ID })}>View outcome</GhostButton>
          </div>
        </section>
      ) : (
        <section className="rounded-2xl border border-primary/25 bg-card p-5">
          <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">Highlighted insight</p>
          <h2 className="mt-1 text-[16px] font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>
            {block.captures[0]?.title}
          </h2>
          <p className="mt-2 max-w-[68ch] text-[13.5px] leading-relaxed text-foreground">{block.captures[0]?.evidence}</p>
          {block.captures[0]?.detail && (
            <div className="mt-3">
              <GhostButton onClick={() => onNav({ pane: "activity", detail: block.captures[0].detail })}>See evidence</GhostButton>
            </div>
          )}
        </section>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        {block.snapshot.map((item) => {
          const value = item.id === "review" && reviewValue ? reviewValue : item.value;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSnapshot(item.opens)}
              className="rounded-2xl border border-white/10 bg-card px-4 py-4 text-left hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
            >
              <span className="block font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">{item.label}</span>
              <span className="mt-1 block text-[20px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                {value}
              </span>
            </button>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <PulseCard title="Connected" hint="Sources feed the worker. Click a worker to open it.">
          <div className="space-y-2">
            {block.workers.map((id) => {
              const worker = WORKERS[id];
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => onNav({ block: block.id, worker: id, detail: null })}
                  className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-white/10 px-3 py-3 text-left hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                >
                  <span>
                    <span className="block text-[9.5px] font-medium uppercase tracking-[0.1em] text-primary">Worker</span>
                    <span className="mt-0.5 block text-[14px] font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                      {workerNames?.[id] ?? worker.name}
                    </span>
                    <span className="mt-0.5 block text-[12.5px] text-slate-400">{worker.role}</span>
                  </span>
                  <span className="shrink-0 text-[12px] font-semibold text-primary">
                    Open <ArrowRight className="ml-0.5 inline size-3.5" />
                  </span>
                </button>
              );
            })}
            <ul className="divide-y divide-white/[0.06] pt-1">
              {block.sources.map((source) => (
                <li key={source.id}>
                  <button
                    type="button"
                    onClick={() => onNav({ detail: source.id })}
                    className="flex min-h-11 w-full items-center justify-between gap-3 py-2.5 text-left"
                  >
                    <span>
                      <span className="block text-[13.5px] font-medium text-foreground">{source.name}</span>
                      <span className="block text-[12px] text-slate-500">{source.role}</span>
                    </span>
                    <IllustrativeMark kind={source.honesty} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </PulseCard>

        <PulseCard title={block.id === "investors" ? "Segments" : "Insights"}>
          <div className="space-y-2">
            {(block.id === "investors" ? block.segments.filter((item) => item.id !== "referrals") : block.segments).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onNav({ detail: item.id })}
                className="flex w-full flex-col rounded-xl border border-white/10 px-3 py-3 text-left hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[14px] font-semibold text-foreground">{item.name}</span>
                  <span className="font-mono text-[11px] text-slate-500">{item.countLabel}</span>
                </span>
                <span className="mt-1 text-[12.5px] text-slate-400">{item.signal}</span>
              </button>
            ))}
          </div>
        </PulseCard>
      </div>
    </>
  );
}

function Activity({
  block,
  onNav,
}: {
  block: BlockContent;
  onNav: (next: Partial<PulseNav>) => void;
}) {
  const referral = useReferral();
  const handoffs = block.conversations.filter((row) => row.handoff);
  const crm = block.sources.find((source) => source.id === "src-crm");

  return (
    <>
      <PulseCard title="Recent conversations" hint="Open a row for the captured exchange." badge={<IllustrativeMark />}>
        {block.conversations.length === 0 ? (
          <p className="text-sm text-slate-500">No conversations on this block yet.</p>
        ) : (
          <ul className="divide-y divide-white/[0.06]">
            {block.conversations.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => onNav({ detail: row.id })}
                  className="flex w-full flex-col py-3 text-left first:pt-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span>
                      <span className="block text-[13.5px] font-medium text-foreground">{row.who}</span>
                      <span className="mt-0.5 block text-[12px] text-slate-500">{row.source} · {row.channel}</span>
                    </span>
                    <PulseChip tone={row.id === "c-referral" ? conversationStage(referral.status).tone : row.stageTone}>
                      {row.id === "c-referral" ? conversationStage(referral.status).stage : row.stage}
                    </PulseChip>
                  </span>
                  <span className="mt-1 text-[12.5px] text-slate-400">{row.learned}</span>
                  <span className="mt-1 font-mono text-[11px] text-slate-500">{row.last}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </PulseCard>

      {(handoffs.length > 0 || crm) && (
        <PulseCard title="Intent and hand-offs">
          <ul className="space-y-3">
            {crm && (
              <li>
                <button type="button" onClick={() => onNav({ detail: crm.id })} className="w-full text-left">
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-[13.5px] font-medium text-foreground">{crm.name}</span>
                    <IllustrativeMark kind={crm.honesty} />
                  </span>
                  <span className="mt-1 block text-[12.5px] text-slate-400">{crm.detail}</span>
                </button>
              </li>
            )}
            {handoffs.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => onNav({ detail: row.id })} className="w-full text-left">
                  <span className="text-[13.5px] font-medium text-foreground">{row.handoff?.label}</span>
                  <span className="mt-1 block text-[12.5px] text-slate-400">{row.handoff?.note}</span>
                </button>
              </li>
            ))}
          </ul>
        </PulseCard>
      )}
    </>
  );
}

function Learning({
  block,
  onNav,
}: {
  block: BlockContent;
  onNav: (next: Partial<PulseNav>) => void;
}) {
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";

  return (
    <>
      <PulseCard title="Patterns and knowledge" hint="Click a row for evidence.">
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

      <PulseCard title="How knowledge changes" hint="Illustrative trail — not a live ledger.">
        {block.id === "investors" && <div className="mb-4"><CompoundingPanel /></div>}
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
      </PulseCard>
    </>
  );
}

function Outcomes({
  block,
  onNav,
}: {
  block: BlockContent;
  onNav: (next: Partial<PulseNav>) => void;
}) {
  const referral = useReferral();

  return (
    <PulseCard title="Recommendations and results" hint="Open a row for the full history.">
      {block.outcomes.length === 0 ? (
        <p className="text-sm text-slate-500">No outcomes on this block yet.</p>
      ) : (
        <ul className="divide-y divide-white/[0.06]">
          {block.outcomes.map((item) => {
            const live = item.id === REFERRAL_ID;
            const tone = live ? statusTone(referral.status) : item.status === "awaiting" ? "warn" : "good";
            const label = live ? statusLabel(referral.status) : item.status === "awaiting" ? "Awaiting you" : "Recorded";
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onNav({ detail: item.id })}
                  className="flex w-full flex-col py-3 text-left first:pt-0"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="text-[13.5px] font-medium text-foreground">{item.title}</span>
                    <PulseChip tone={tone}>{label}</PulseChip>
                  </span>
                  <span className="mt-1 text-[12.5px] text-slate-400">{item.summary}</span>
                  <span className="mt-1 font-mono text-[11px] text-slate-500">{item.when}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </PulseCard>
  );
}
