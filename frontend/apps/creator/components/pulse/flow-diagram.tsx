import type { ReactNode } from "react";
import { WORKERS, type WorkerId } from "@/components/intelligence-layer/model";
import type { BlockContent } from "./drilldown-data";
import { PulseChip } from "./pulse-chrome";

export function FlowDiagram({
  block,
  workerNames,
  onSource,
  onWorker,
}: {
  block: BlockContent;
  workerNames?: Partial<Record<WorkerId, string>>;
  onSource: (id: string) => void;
  onWorker: (id: WorkerId) => void;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.1fr)_auto_minmax(0,.9fr)] md:items-center">
      <Column label="Connected sources">
        {block.sources.map((source) => (
          <button
            key={source.id}
            type="button"
            onClick={() => onSource(source.id)}
            className="flex min-h-11 w-full flex-col rounded-xl border border-border bg-card px-3 py-2.5 text-left hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            <span className="text-[13px] font-semibold text-foreground">{source.name}</span>
            <span className="text-[11px] text-slate-500">{source.role}</span>
          </button>
        ))}
      </Column>
      <Arrow />
      <Column label="Workers · click one">
        {block.workers.map((id) => {
          const worker = WORKERS[id];
          return (
            <button
              key={id}
              type="button"
              onClick={() => onWorker(id)}
              className="flex min-h-[72px] w-full flex-col rounded-2xl border border-border bg-card px-3 py-3 text-left hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
            >
              <span className="text-[9.5px] font-medium uppercase tracking-[0.1em] text-primary">Worker</span>
              <span className="mt-0.5 text-[14px] font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                {workerNames?.[id] ?? worker.name}
              </span>
              <span className="mt-1 text-[12px] text-slate-400">{worker.purpose}</span>
            </button>
          );
        })}
      </Column>
      <Arrow />
      <Column label="This knowledge">
        <div className="flex min-h-[88px] flex-col items-center justify-center rounded-full border-2 border-primary/30 bg-card px-4 py-6 text-center">
          <span className="text-[15px] font-extrabold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{block.name}</span>
          <span className="mt-1 font-mono text-[10px] text-slate-500">Then company intelligence</span>
          <PulseChip tone="blue">Shared record</PulseChip>
        </div>
      </Column>
    </div>
  );
}

function Column({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-[10px] tracking-[0.12em] text-slate-500 uppercase">{label}</p>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

function Arrow() {
  return (
    <p className="hidden text-center font-mono text-[11px] text-slate-500 md:block" aria-hidden>
      →
    </p>
  );
}
