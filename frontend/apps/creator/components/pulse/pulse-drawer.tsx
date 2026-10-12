"use client";

import type { ReactNode } from "react";
import { ArrowRight, Ban, BookOpen, Eye, Shield } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import {
  RECORD,
  SYSTEM_DETAIL,
  WORKERS,
  isWorkerId,
  type FocusId,
  type SystemId,
  type WorkerId,
} from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { useBrain } from "@/lib/brain/store";
import { CompoundingPanel } from "./compounding";
import { PULSE_BLOCKS, pulseNode } from "./nodes";
import { GhostButton, PulseChip } from "./pulse-chrome";
import { REFERRAL, decisionLabel, statusLabel, statusTone } from "./referral";
import { companyIntel } from "./record-summary";
import type { PulseNav } from "./route";

export function PulseDrawer({
  focus,
  workerNames,
  onClose,
  onSelect,
  onOpen,
  onNav,
}: {
  focus: FocusId | null;
  workerNames?: Partial<Record<WorkerId, string>>;
  onClose: () => void;
  onSelect: (id: FocusId) => void;
  onOpen: (id: FocusId) => void;
  onNav?: (next: Partial<PulseNav>) => void;
}) {
  const node = focus ? pulseNode(focus, workerNames) : null;
  const referral = useReferral();
  const brain = useBrain();
  const intel = companyIntel(referral.status, brain.approval);
  const summary = focus ? intel.hover[focus] ?? node?.summary : "";

  return (
    <Dialog open={Boolean(focus)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        className="fixed inset-y-0 right-0 top-0 left-auto flex h-full max-h-none w-full max-w-[min(440px,100%)] translate-x-0 translate-y-0 flex-col gap-0 overflow-y-auto rounded-none border-y-0 border-l border-white/10 bg-popover text-popover-foreground p-0 shadow-[-20px_0_50px_-20px_rgba(0,0,0,.65)] sm:max-w-[min(440px,100%)] data-[state=open]:zoom-in-100"
        aria-describedby={undefined}
      >
        {node && focus && (
          <>
            <DialogHeader className="border-b border-white/10 px-6 py-5 text-left">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-violet-400">{node.kicker}</p>
              <div className="mt-1 flex items-start justify-between gap-3">
                <DialogTitle className="text-[19px] font-extrabold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                  {node.name}
                </DialogTitle>
                <HonestyBadge kind="illustrative" />
              </div>
              <DialogDescription className="text-[13.5px] leading-relaxed text-slate-400">{summary}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-1 flex-col gap-5 px-6 py-5">
              {isWorkerId(focus) ? (
                <WorkerBody id={focus} onSelect={onSelect} onOpen={onOpen} />
              ) : focus === "record" ? (
                <RecordBody onOpen={onOpen} onNav={onNav} />
              ) : (
                <BlockBody id={focus} onSelect={onSelect} onOpen={onOpen} />
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function WorkerBody({
  id,
  onSelect,
  onOpen,
}: {
  id: WorkerId;
  onSelect: (id: FocusId) => void;
  onOpen: (id: FocusId) => void;
}) {
  const worker = WORKERS[id];
  const blockId = id === "property-insights" ? "properties" : "investor-app";
  return (
    <>
      <Section icon={BookOpen} title="Purpose">{worker.purpose}</Section>
      <Section icon={Shield} title="Restrictions">
        <ul className="space-y-2">
          {worker.hardWalls.map((item) => (
            <li key={item} className="flex gap-2 text-[13.5px] text-foreground">
              <Ban className="mt-0.5 size-3.5 shrink-0 text-red-400" />
              {item}
            </li>
          ))}
        </ul>
      </Section>
      <Section icon={BookOpen} title="Recent actions">
        <ul className="space-y-2">
          {worker.runs.map((row) => (
            <li key={row.id} className="rounded-xl bg-muted px-3 py-2.5">
              <p className="font-mono text-[11px] text-slate-500">{row.time}</p>
              <p className="mt-1 text-[13px] text-foreground">{row.result}</p>
            </li>
          ))}
        </ul>
      </Section>
      <div className="flex flex-wrap gap-2">
        <TextLink onClick={() => onOpen(id)}>
          Open worker <ArrowRight className="size-3.5" />
        </TextLink>
        <TextLink onClick={() => onOpen(blockId)}>
          Open {id === "property-insights" ? "Properties" : "Investors"}
        </TextLink>
        <TextLink onClick={() => onSelect("record")}>Company record</TextLink>
      </div>
    </>
  );
}

function BlockBody({
  id,
  onSelect,
  onOpen,
}: {
  id: SystemId;
  onSelect: (id: FocusId) => void;
  onOpen: (id: FocusId) => void;
}) {
  const detail = SYSTEM_DETAIL[id];
  const isBlock = PULSE_BLOCKS.includes(id);
  return (
    <>
      <Section icon={Eye} title="What this is">{detail.purpose}</Section>
      {detail.allowed.length > 0 && (
        <Section icon={Eye} title="Allowed">
          <List items={detail.allowed} />
        </Section>
      )}
      {detail.blocked.length > 0 && (
        <Section icon={Ban} title="Hard walls">
          <List items={detail.blocked} />
        </Section>
      )}
      <div className="flex flex-wrap gap-2">
        {isBlock && (
          <TextLink onClick={() => onOpen(id)}>
            Open {id === "properties" ? "Properties" : "Investors"} block <ArrowRight className="size-3.5" />
          </TextLink>
        )}
        <TextLink onClick={() => onSelect("record")}>Company record</TextLink>
      </div>
    </>
  );
}

function RecordBody({
  onOpen,
  onNav,
}: {
  onOpen: (id: FocusId) => void;
  onNav?: (next: Partial<PulseNav>) => void;
}) {
  const referral = useReferral();
  const brain = useBrain();
  const intel = companyIntel(referral.status, brain.approval);
  const decided = referral.status === "approved" || referral.status === "rejected";

  return (
    <>
      <p className="text-[13px] leading-relaxed text-slate-400">{RECORD.purpose}</p>

      <Section icon={BookOpen} title="Referral decision">
        <div className="flex flex-wrap items-center gap-2">
          <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
        </div>
        <p className="mt-2 text-[13.5px] font-medium text-foreground">{REFERRAL.title}</p>
        <p className="mt-1 text-[12.5px] text-foreground">{decisionLabel(referral.status)}</p>
        {referral.decidedAt && <p className="mt-1 font-mono text-[11px] text-slate-500">Recorded at {referral.decidedAt}.</p>}
        {decided && <div className="mt-3"><CompoundingPanel compact /></div>}
        {onNav && (
          <div className="mt-3 flex flex-wrap gap-2">
            <GhostButton onClick={() => onNav({ block: "investors", pane: "outcomes", detail: REFERRAL.id, focus: null })}>
              Open outcome
            </GhostButton>
            <GhostButton onClick={() => onOpen("investor-app")}>Open Investors</GhostButton>
          </div>
        )}
      </Section>

      <Section icon={BookOpen} title="Knowledge blocks">
        <ul className="space-y-2">
          {intel.blocks.map((block) => (
            <li key={block.id}>
              <button
                type="button"
                onClick={() => onOpen(block.id)}
                className="flex min-h-11 w-full flex-col rounded-xl border border-white/10 px-3 py-3 text-left hover:border-primary/40"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[14px] font-semibold text-foreground">{block.name}</span>
                  <span className="text-[12px] font-semibold text-primary">Open</span>
                </span>
                <span className="mt-1 text-[12.5px] text-slate-400">{block.worker} · {block.signal}</span>
              </button>
            </li>
          ))}
        </ul>
      </Section>

      <Section icon={BookOpen} title="Added over time">
        <ol className="space-y-2">
          {intel.timeline.map((row) => (
            <li key={row.month} className="grid grid-cols-[40px_minmax(0,1fr)] gap-2 text-[13px]">
              <span className="font-mono text-slate-500">{row.month}</span>
              <span className="text-foreground">{row.note}</span>
            </li>
          ))}
        </ol>
      </Section>

      {!decided && (
      <Section icon={BookOpen} title="Latest learning">
        <p className="text-[13.5px] font-medium text-foreground">{intel.latestLearning.title}</p>
        <p className="mt-1 text-[12.5px] text-slate-400">{intel.latestLearning.evidence}</p>
        <div className="mt-2"><PulseChip tone="blue">{intel.latestLearning.label}</PulseChip></div>
      </Section>
      )}

      <Section icon={Eye} title="Needs a person">
        {intel.awaiting.length === 0 ? (
          <p>Nothing waiting on a decision.</p>
        ) : (
          <ul className="space-y-2">
            {intel.awaiting.map((item) => (
              <li key={item.title}>
                <button
                  type="button"
                  onClick={() => onOpen(item.origin)}
                  className="w-full rounded-lg text-left text-[13.5px] text-foreground hover:text-primary"
                >
                  {item.title}
                  <span className="mt-0.5 block font-mono text-[11px] text-slate-500">{item.when}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

function Section({ icon: Icon, title, children }: { icon: typeof Eye; title: string; children: ReactNode }) {
  return (
    <section>
      <p className="mb-2 flex items-center gap-1.5 font-mono text-[10.5px] font-medium uppercase tracking-[0.1em] text-slate-500">
        <Icon className="size-3.5" /> {title}
      </p>
      <div className="text-[13.5px] leading-relaxed text-slate-400">{children}</div>
    </section>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5 text-[13.5px] text-foreground">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function TextLink({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-11 items-center gap-1 rounded-lg px-3 text-[13px] font-semibold text-primary hover:underline"
    >
      {children}
    </button>
  );
}
