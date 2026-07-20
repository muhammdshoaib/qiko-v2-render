"use client";

// Cockpit landing view: lists every tender (RFP pack) for this worker with its due date and live
// status, so the user opens the cockpit on an overview of ALL tenders and drills into one, rather
// than landing straight on a single tender behind a dropdown. Selecting a row picks that pack and
// switches to the tender's Overview tab. Status/outcome pills mirror the Worker Overview tenders
// list (app/workers/[id]/page.tsx) for cross-view consistency.
import { Building2, Check, FileText, Plus, X } from "lucide-react";
import { cn } from "@qiko/ui";
import type { RfpPack } from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";

// Live tender status from the generation pipeline (the stepper's source of truth), NOT the legacy
// pack.stage, which the stepper flow no longer advances so it would read "parsed" forever. Kept in
// step with tenderStatusLabel/tenderStatusClass on the Worker Overview page.
function tenderStatusLabel(p: RfpPack): string {
  const g = p.gen_status;
  const drafts = g?.drafts?.state;
  if (drafts === "ready") return "Ready for review";
  if (drafts === "partial") return "Drafting (partial)";
  if (drafts === "running" || drafts === "pending") return "Drafting";
  if (g?.sections === "error" || g?.requirements === "error") return "Parse error";
  if (g?.sections === "running" || g?.sections === "pending" || g?.requirements === "running" || g?.requirements === "pending") return "Parsing";
  return p.stage || "parsed";
}

function tenderStatusClass(p: RfpPack): string {
  const drafts = p.gen_status?.drafts?.state;
  if (drafts === "ready") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (drafts === "partial") return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  if (drafts === "running" || drafts === "pending") return "border-indigo-500/30 bg-indigo-500/10 text-indigo-300";
  if (p.gen_status?.sections === "error" || p.gen_status?.requirements === "error") return "border-red-500/30 bg-red-500/10 text-red-400";
  return "border-white/10 bg-white/[0.04] text-slate-400";
}

function OutcomePill({ outcome }: { outcome: RfpPack["outcome"] }) {
  if (!outcome) return <span className="text-[12px] text-slate-600">-</span>;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold capitalize",
      outcome === "won" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
        : outcome === "lost" ? "border-red-500/30 bg-red-500/10 text-red-400"
          : "border-white/10 bg-white/[0.04] text-slate-400")}>
      {outcome === "won" ? <Check className="size-3" /> : outcome === "lost" ? <X className="size-3" /> : null}
      {outcome}
    </span>
  );
}

export function TendersListView({ packs, onOpen, onNewTender }: {
  packs: RfpPack[];
  /** Select a tender and drill into it (picks the pack + switches to its Overview tab). */
  onOpen: (packId: string) => void;
  onNewTender: () => void;
}) {
  const count = packs.length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-white">Tenders</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">
            {count === 0 ? "No tenders yet" : `${count} tender${count === 1 ? "" : "s"}`}
          </p>
        </div>
        <button
          onClick={onNewTender}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
        >
          <Plus className="size-4" /> New tender
        </button>
      </div>

      {count === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
          <FileText className="mb-3 size-9 text-slate-600" />
          <p className="text-sm font-semibold text-white">No tenders yet</p>
          <p className="mt-1 max-w-xs text-[13px] text-slate-500">
            Upload your first RFP to start drafting a grounded response.
          </p>
          <button
            onClick={onNewTender}
            className="mt-5 inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            <Plus className="size-4" /> New tender
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.015]">
          {/* Column headers (lg+ only; each row is a self-describing card on smaller screens). */}
          <div className="hidden grid-cols-[minmax(0,2fr)_minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.8fr)] gap-3 border-b border-white/[0.06] px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 lg:grid">
            <span>Tender</span>
            <span>Client</span>
            <span>Due date</span>
            <span>Status</span>
            <span>Outcome</span>
          </div>

          <ul className="divide-y divide-white/[0.06]">
            {packs.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => onOpen(p.id)}
                  className="grid w-full grid-cols-1 gap-2 px-4 py-3 text-left transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400/60 lg:grid-cols-[minmax(0,2fr)_minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.8fr)] lg:items-center lg:gap-3"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium text-white">{p.title}</span>
                  </span>
                  <span className="flex min-w-0 items-center gap-1.5 text-[12px] text-slate-400">
                    <Building2 className="size-3.5 shrink-0 text-slate-500 lg:hidden" />
                    <span className="truncate">{p.client_name || "No client set"}</span>
                  </span>
                  <span className="text-[12px] text-slate-400">
                    <span className="text-slate-500 lg:hidden">Due </span>{formatShortDate(p.deadline)}
                  </span>
                  <span>
                    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", tenderStatusClass(p))}>
                      {tenderStatusLabel(p)}
                    </span>
                  </span>
                  <span>
                    <OutcomePill outcome={p.outcome} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
