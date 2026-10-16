"use client";

import { ArrowRight } from "lucide-react";
import { WORKERS, type WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { BLOCKS, KNOWLEDGE_LAYER, LEARNING_LABEL, type BlockContent, type SnapshotItem } from "./drilldown-data";
import { EvidenceDrawer } from "./evidence-drawer";
import { GhostButton, IllustrativeMark, PulseCard, PulseChip, PulseHeader, PulsePage, PulseTabs } from "./pulse-chrome";
import { REFERRAL, REFERRAL_EVIDENCE_ID, REFERRAL_ID, conversationStage, decisionLabel, isDecided, statusLabel, statusTone } from "./referral";
import type { BlockPane, PulseNav } from "./route";
import { blockPane } from "./route";

const TABS: { id: BlockPane; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "activity", label: "Activity" },
  { id: "learning", label: "Learning" },
  { id: "outcomes", label: "Insights" },
];

export function BlockView({
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
  const block = BLOCKS[nav.block ?? "investors"];
  const pane = blockPane(nav.pane);

  const openSnapshot = (item: SnapshotItem) => {
    if (item.opens === "activity" || item.id === "active") onNav({ pane: "activity", detail: item.detail ?? null });
    else if (item.opens === "segments") onNav({ pane: "overview", detail: item.detail ?? null });
    else if (item.opens === "worker") onNav({ block: block.id, worker: block.workers[0], detail: null });
    else if (item.opens === "review") {
      onNav({
        pane: block.id === "investors" ? "outcomes" : "activity",
        detail: item.detail ?? (block.id === "investors" ? REFERRAL_ID : "c-spend"),
      });
    }
    else if (item.opens === "record") onNav({ pane: "learning", detail: null });
    else onNav({ pane: "overview", detail: item.detail ?? null });
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
        onDeferReferral={onDeferReferral}
      />
    </PulsePage>
  );
}

function Overview({
  block,
  workerNames,
  onNav,
  onSnapshot,
}: {
  block: BlockContent;
  workerNames?: Partial<Record<WorkerId, string>>;
  onNav: (next: Partial<PulseNav>) => void;
  onSnapshot: (item: SnapshotItem) => void;
}) {
  const referral = useReferral();

  return (
    <>
      {block.id === "investors" ? (
        <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3.5">
          <div>
            <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">
              {isDecided(referral.status) ? "Latest decision" : referral.status === "deferred" ? "Deferred" : "Awaiting a person"}
            </p>
            <p className="mt-0.5 text-[13.5px] text-foreground">{REFERRAL.title}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
            <GhostButton onClick={() => onNav({ pane: "activity", detail: REFERRAL_EVIDENCE_ID })}>See evidence</GhostButton>
            <GhostButton onClick={() => onNav({ pane: "outcomes", detail: REFERRAL_ID })}>Open Insights</GhostButton>
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

      <div className={block.snapshot.length > 3 ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-4" : "grid gap-3 sm:grid-cols-3"}>
        {block.snapshot.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onSnapshot(item)}
            className="rounded-2xl border border-border bg-card px-4 py-4 text-left hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            <span className="block font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">{item.label}</span>
            <span className="mt-1 block text-[20px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
              {item.value}
            </span>
            <span className="mt-1.5 block text-[11.5px] leading-snug text-slate-500">{item.hint}</span>
            {item.honesty && (
              <span className="mt-2 block">
                <IllustrativeMark kind={item.honesty} />
              </span>
            )}
          </button>
        ))}
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
                  className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-border px-3 py-3 text-left hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
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
            <ul className="divide-y divide-border pt-1">
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
                className="flex w-full flex-col rounded-xl border border-border px-3 py-3 text-left hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
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
          <ul className="divide-y divide-border">
            {block.conversations.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => onNav({ detail: row.id })}
                  className="flex w-full flex-col py-3 text-left first:pt-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
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
  const decided = isDecided(referral.status);
  const measured = referral.status === "approved"
    ? REFERRAL.recordedResult.approved
    : referral.status === "rejected"
      ? REFERRAL.recordedResult.rejected
      : REFERRAL.recordedResult.pending;

  if (block.id !== "investors") {
    return (
      <PulseCard title="Patterns and knowledge" hint="Click a row for evidence.">
        <ul className="divide-y divide-border">
          {block.learnings.map((item) => {
            const state = LEARNING_LABEL[item.state];
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
    );
  }

  const observations = block.learnings.filter((item) => item.id === "l-referral" || item.id === "l-review" || item.id === "l-quiet");
  const walls = block.learnings.filter((item) => item.state === "rule");
  const decisionTone = referral.status === "approved" ? "good" : referral.status === "rejected" ? "bad" : "warn";

  return (
    <>
      <PulseCard title="Observed" hint="What the Intelligence Worker noticed, and the evidence behind it.">
        <ul className="divide-y divide-border">
          {observations.map((item) => (
            <li key={item.id} className="flex flex-col gap-2 py-3 first:pt-0 sm:flex-row sm:items-start sm:justify-between">
              <button type="button" onClick={() => onNav({ detail: item.id })} className="text-left">
                <p className="text-[13.5px] font-medium text-foreground">{item.title}</p>
                <p className="mt-1 text-[12.5px] text-slate-400">{item.evidence}</p>
              </button>
              <PulseChip tone={KNOWLEDGE_LAYER.observation.tone}>{KNOWLEDGE_LAYER.observation.label}</PulseChip>
            </li>
          ))}
        </ul>
        {walls.length > 0 && (
          <p className="mt-3 text-[12.5px] text-slate-500">
            Hard walls in force: {walls.map((item) => item.title.toLowerCase()).join(" · ")}.
          </p>
        )}
      </PulseCard>

      <PulseCard title="Recommendation and decision" hint="A person still writes this to the company record.">
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => onNav({ pane: "outcomes", detail: REFERRAL_ID })}
            className="flex w-full flex-col rounded-xl border border-border px-3 py-3 text-left hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 sm:flex-row sm:items-start sm:justify-between"
          >
            <span>
              <span className="block text-[13.5px] font-medium text-foreground">{REFERRAL.title}</span>
              <span className="mt-1 block text-[12.5px] text-slate-400">{REFERRAL.action}</span>
            </span>
            <PulseChip tone={KNOWLEDGE_LAYER.recommendation.tone}>{KNOWLEDGE_LAYER.recommendation.label}</PulseChip>
          </button>
          <div className="rounded-xl border border-border bg-muted px-3 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[13.5px] font-medium text-foreground">
                {decided ? decisionLabel(referral.status) : "Nothing captured yet. Approve or decline on Insights to write this to the company record."}
              </p>
              <PulseChip tone={decisionTone}>{KNOWLEDGE_LAYER.decision.label}</PulseChip>
            </div>
            {decided && (
              <div className="mt-3">
                <p className="text-[12.5px] text-slate-400">This now sits on October in company knowledge.</p>
                <div className="mt-2">
                  <GhostButton onClick={() => onNav({ block: null, worker: null, detail: null, focus: "record" })}>
                    View company timeline
                  </GhostButton>
                </div>
              </div>
            )}
            {!decided && (
              <div className="mt-3">
                <GhostButton onClick={() => onNav({ pane: "outcomes", detail: REFERRAL_ID })}>Open Insights</GhostButton>
              </div>
            )}
          </div>
        </div>
      </PulseCard>

      <PulseCard title="Measured outcome" hint="What can be claimed after a human decision — not a forecast.">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="max-w-[68ch] text-[13.5px] leading-relaxed text-foreground">{measured}</p>
          <PulseChip tone={KNOWLEDGE_LAYER.outcome.tone}>{KNOWLEDGE_LAYER.outcome.label}</PulseChip>
        </div>
        <p className="mt-2 text-[12.5px] text-slate-500">{REFERRAL.caution}</p>
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
        <p className="text-sm text-slate-500">No insights on this block yet.</p>
      ) : (
        <ul className="divide-y divide-border">
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
