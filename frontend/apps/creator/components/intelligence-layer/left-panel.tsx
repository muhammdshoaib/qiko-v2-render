"use client";

import { Button, cn } from "@qiko/ui";
import { WorkerInspector } from "./worker-inspector";
import { CRM_AGENT, type EdgeId, type FocusId } from "./model";

export function LeftPanel({
  focus,
  capturedCount,
  onSelectWorker,
  onSelectEvidence,
  onShowAll,
}: {
  focus: FocusId | null;
  capturedCount?: number;
  onSelectWorker: () => void;
  onSelectEvidence: (edgeId: EdgeId) => void;
  onShowAll: () => void;
}) {
  return (
    <aside className="flex h-full min-h-0 flex-col overflow-y-auto rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
      <div className="mb-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Workers</h2>
        <p className="mt-1 text-[12px] text-slate-400">Select a worker to inspect purpose, permissions, and walls.</p>
        <button
          type="button"
          aria-pressed={focus === "crm-agent"}
          onClick={onSelectWorker}
          className={cn(
            "mt-3 w-full rounded-xl border px-3 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
            focus === "crm-agent" ? "border-cyan-400/40 bg-cyan-400/10" : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]",
          )}
        >
          <p className="text-sm font-medium text-white">{CRM_AGENT.name}</p>
          <p className="mt-1 text-[12px] text-slate-400">{CRM_AGENT.role}</p>
          <p className="mt-2 text-[11px] text-slate-500">{capturedCount ?? CRM_AGENT.decisions} captured decisions · prototype</p>
        </button>
      </div>

      {focus ? (
        <>
          <WorkerInspector focus={focus} capturedCount={capturedCount} onSelectEvidence={onSelectEvidence} />
          <Button type="button" variant="outline" className="mt-auto w-full" onClick={onShowAll}>
            Clear selection
          </Button>
        </>
      ) : (
        <p className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-[13px] text-slate-500">
          Click the CRM Agent, a system, or the Qiko record to inspect it.
        </p>
      )}
    </aside>
  );
}
