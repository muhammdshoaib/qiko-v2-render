"use client";

import { Button, cn } from "@qiko/ui";
import { WorkerInspector } from "./worker-inspector";
import { WORKERS, WORKER_IDS, type EdgeId, type FocusId, type WorkerId } from "./model";

export function LeftPanel({
  focus,
  capturedCount,
  onSelectWorker,
  onSelectEvidence,
  onShowAll,
}: {
  focus: FocusId | null;
  capturedCount?: number;
  onSelectWorker: (id: WorkerId) => void;
  onSelectEvidence: (edgeId: EdgeId) => void;
  onShowAll: () => void;
}) {
  return (
    <aside className="flex h-full min-h-0 flex-col overflow-y-auto rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
      <div className="mb-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Workers</h2>
        <p className="mt-1 text-[12px] text-slate-400">Select a worker to see what it can read, write, and must not do.</p>
        <div className="mt-3 space-y-2">
          {WORKER_IDS.map((id) => {
            const worker = WORKERS[id];
            return (
              <button
                key={id}
                type="button"
                aria-pressed={focus === id}
                onClick={() => onSelectWorker(id)}
                className={cn(
                  "w-full rounded-xl border px-3 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                  focus === id ? "border-cyan-400/40 bg-cyan-400/10" : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]",
                )}
              >
                <p className="text-sm font-medium text-white">{worker.name}</p>
                <p className="mt-1 text-[12px] text-slate-400">{worker.role}</p>
                <p className="mt-1 text-[11px] text-slate-500">{worker.decisions} outcomes · sample</p>
              </button>
            );
          })}
        </div>
        {capturedCount != null && (
          <p className="mt-3 text-[11px] text-slate-500">{capturedCount} captured outcomes · sample</p>
        )}
      </div>

      {focus ? (
        <>
          <WorkerInspector focus={focus} capturedCount={capturedCount} onSelectEvidence={onSelectEvidence} />
          <Button type="button" variant="outline" className="mt-auto w-full" onClick={onShowAll}>
            Show all workers
          </Button>
        </>
      ) : (
        <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-[13px] text-slate-400">
          <p>Company intelligence sits in the centre.</p>
          <p className="mt-2 text-slate-500">Click a worker to highlight its systems, knowledge, and walls.</p>
        </div>
      )}
    </aside>
  );
}
