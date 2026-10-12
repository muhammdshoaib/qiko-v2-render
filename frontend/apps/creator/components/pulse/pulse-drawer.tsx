"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Ban, BookOpen, Eye, Shield } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import {
  EDGES,
  RECORD,
  SYSTEM_DETAIL,
  SYSTEMS,
  WORKERS,
  isWorkerId,
  type FocusId,
  type SystemId,
  type WorkerId,
} from "@/components/intelligence-layer/model";
import { pulseNode } from "./nodes";

export function PulseDrawer({
  focus,
  workerNames,
  onClose,
  onSelect,
}: {
  focus: FocusId | null;
  workerNames?: Partial<Record<WorkerId, string>>;
  onClose: () => void;
  onSelect: (id: FocusId) => void;
}) {
  const node = focus ? pulseNode(focus, workerNames) : null;

  return (
    <Dialog open={Boolean(focus)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        className="fixed inset-y-0 right-0 top-0 left-auto flex h-full max-h-none w-full max-w-[min(540px,100%)] translate-x-0 translate-y-0 flex-col gap-0 overflow-y-auto rounded-none border-y-0 border-l border-white/10 bg-popover text-popover-foreground p-0 shadow-[-20px_0_50px_-20px_rgba(0,0,0,.65)] sm:max-w-[min(540px,100%)] data-[state=open]:zoom-in-100"
        aria-describedby={undefined}
      >
        {node && (
          <>
            <DialogHeader className="border-b border-white/10 px-6 py-5 text-left">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-violet-400">{node.kicker}</p>
              <div className="mt-1 flex items-start justify-between gap-3">
                <DialogTitle className="text-[19px] font-extrabold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                  {node.name}
                </DialogTitle>
                <HonestyBadge kind="illustrative" />
              </div>
              <DialogDescription className="text-[13.5px] leading-relaxed text-slate-400">{node.summary}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-1 flex-col gap-5 px-6 py-5">
              {focus && isWorkerId(focus) ? (
                <WorkerBody id={focus} onSelect={onSelect} />
              ) : focus === "record" ? (
                <RecordBody onSelect={onSelect} />
              ) : focus ? (
                <BlockBody id={focus} onSelect={onSelect} />
              ) : null}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function WorkerBody({ id, onSelect }: { id: WorkerId; onSelect: (id: FocusId) => void }) {
  const worker = WORKERS[id];
  return (
    <>
      <Section icon={BookOpen} title="Purpose">{worker.purpose}</Section>
      <Section icon={Eye} title="Reads">
        <ul className="space-y-2">
          {worker.reads.map((item) => (
            <li key={item.title}>
              <p className="text-[13.5px] font-medium text-foreground">{item.title}</p>
              <p className="text-[12.5px] text-slate-400">{item.detail}</p>
            </li>
          ))}
        </ul>
      </Section>
      <Section icon={BookOpen} title="Writes">
        <ul className="space-y-2">
          {worker.writes.map((item) => (
            <li key={item.title} className="text-[13.5px] text-foreground">{item.title}</li>
          ))}
        </ul>
      </Section>
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
        <button type="button" onClick={() => onSelect("record")} className="min-h-11 rounded-lg px-3 text-[13px] font-semibold text-primary hover:underline">
          Company record
        </button>
        <Link href={`/studio/w/${id}`} className="inline-flex min-h-11 items-center rounded-lg px-3 text-[13px] font-semibold text-foreground hover:underline">
          Open worker
        </Link>
      </div>
    </>
  );
}

function BlockBody({ id, onSelect }: { id: SystemId; onSelect: (id: FocusId) => void }) {
  const detail = SYSTEM_DETAIL[id];
  const edges = EDGES.filter((edge) => edge.to === id || edge.from === id);
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
      <Section icon={BookOpen} title="Connected workers">
        <ul className="space-y-1">
          {edges.map((edge) => {
            const other = edge.from === id ? edge.to : edge.from;
            return (
            <li key={edge.id}>
              <button
                type="button"
                onClick={() => onSelect(other)}
                className="min-h-11 w-full rounded-lg px-1 text-left text-[13.5px] text-primary hover:underline"
              >
                {isWorkerId(other) ? WORKERS[other].name : pulseNode(other).name}
              </button>
            </li>
            );
          })}
        </ul>
      </Section>
      <p className="text-[12px] text-slate-500">{SYSTEMS[id].subtitle}</p>
    </>
  );
}

function RecordBody({ onSelect }: { onSelect: (id: FocusId) => void }) {
  return (
    <>
      <Section icon={BookOpen} title="What is written here">{RECORD.purpose}</Section>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => onSelect("property-insights")} className="min-h-11 rounded-lg px-3 text-[13px] font-semibold text-primary hover:underline">
          Property Insights
        </button>
        <button type="button" onClick={() => onSelect("intent-intelligence")} className="min-h-11 rounded-lg px-3 text-[13px] font-semibold text-primary hover:underline">
          Intelligence Worker
        </button>
      </div>
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
