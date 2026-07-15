"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, GripVertical } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  listAgents, listSalesOpportunities, updateSalesOpportunity, type OpportunityStage, type SalesOpportunity,
} from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import {
  deadlineLabel, deadlineUrgencyClass, formatDate, formatMoney, humanize, scoreBadgeClass,
  sourceLabel, stageBadgeClass, STAGE_LABELS,
} from "@/components/sales-intelligence/utils";

const KANBAN_COLUMNS: OpportunityStage[] = ["ingested", "qualifying", "qualified", "validated", "pushed"];
const TERMINAL_STAGES: OpportunityStage[] = ["rejected", "push_failed"];
// Stages a card can be moved to via the keyboard-accessible "Move to…" control (mirrors the
// drag-and-drop board columns so keyboard/screen-reader users have the same reach).
const MOVE_TARGETS: OpportunityStage[] = [...KANBAN_COLUMNS, ...TERMINAL_STAGES];

export default function SalesIntelligencePipelinePage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [view, setView] = useState<"pipeline" | "list">("pipeline");
  const [draggingId, setDraggingId] = useState<number | null>(null);

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const oppsQ = useQuery({ queryKey: ["sales-opportunities", agentId], queryFn: () => listSalesOpportunities(agentId), retry: false });
  const opps: SalesOpportunity[] = oppsQ.data?.opportunities ?? [];

  const moveStage = useMutation({
    mutationFn: (vars: { id: number; stage: OpportunityStage }) => updateSalesOpportunity(agentId, vars.id, { stage: vars.stage }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] }),
  });

  const metrics = useMemo(() => {
    const pushed = opps.filter((o) => o.stage === "pushed").length;
    const upcoming = opps.filter((o) => {
      if (!o.deadlineAt) return false;
      const days = (new Date(o.deadlineAt).getTime() - Date.now()) / 86400000;
      return days >= 0 && days <= 14;
    }).length;
    const lastScan = opps.map((o) => o.createdAt).filter(Boolean).sort().slice(-1)[0];
    const sources = Array.from(new Set(opps.map((o) => (o.sourceKey || "").toUpperCase()).filter(Boolean)));
    return { total: opps.length, pushed, upcoming, lastScan, sources };
  }, [opps]);

  const byStage = useMemo(() => {
    const map = new Map<OpportunityStage, SalesOpportunity[]>();
    for (const stage of [...KANBAN_COLUMNS, ...TERMINAL_STAGES]) map.set(stage, []);
    for (const o of opps) {
      if (!map.has(o.stage)) map.set(o.stage, []);
      map.get(o.stage)!.push(o);
    }
    return map;
  }, [opps]);

  function onDrop(stage: OpportunityStage) {
    if (draggingId == null) return;
    const opp = opps.find((o) => o.id === draggingId);
    if (opp && opp.stage !== stage) moveStage.mutate({ id: draggingId, stage });
    setDraggingId(null);
  }

  function onMove(id: number, stage: OpportunityStage) {
    const opp = opps.find((o) => o.id === id);
    if (opp && opp.stage !== stage) moveStage.mutate({ id, stage });
  }

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="pipeline">
      <div className="space-y-6">
        <OutcomesStrip title="OPPORTUNITY PIPELINE" tiles={[
          { value: String(metrics.total), label: "Total in Pipeline", caption: "all stages", trend: "up" },
          { value: String(metrics.pushed), label: "Pushed to Salesforce", caption: "successfully synced", trend: "up" },
          { value: String(metrics.upcoming), label: "Upcoming Deadlines", caption: "within 14 days", trend: metrics.upcoming > 0 ? "down" : "neutral" },
          { value: formatDate(metrics.lastScan, true), label: "Last Portal Scan", caption: metrics.sources.join(" \u00b7 ") || "\u2014", trend: "up" },
        ]} />

        <div className="inline-flex rounded-lg border border-white/10 bg-white/[0.02] p-0.5">
          {(["pipeline", "list"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              aria-pressed={view === v}
              className={cn("rounded-md px-3.5 py-1.5 text-[13px] font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                view === v ? "bg-indigo-500/20 text-white" : "text-slate-400 hover:text-white")}>
              {v}
            </button>
          ))}
        </div>

        {oppsQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {oppsQ.isError && <p className="text-sm text-red-400">Couldn&apos;t load the pipeline. Try refreshing.</p>}

        {view === "pipeline" ? (
          <div className="space-y-6">
            <div className="flex gap-4 overflow-x-auto pb-2">
              {KANBAN_COLUMNS.map((stage) => (
                <div key={stage} onDragOver={(e) => e.preventDefault()} onDrop={() => onDrop(stage)}
                  className="flex w-[260px] shrink-0 flex-col rounded-xl border border-white/[0.06] bg-white/[0.01]">
                  <div className="flex items-center justify-between border-b border-white/[0.06] px-3.5 py-3">
                    <span className="text-[13px] font-semibold text-white">{STAGE_LABELS[stage]}</span>
                    <span className="flex size-5 items-center justify-center rounded-full bg-white/[0.06] text-[11px] font-semibold text-slate-300">
                      {byStage.get(stage)?.length ?? 0}
                    </span>
                  </div>
                  <div className="flex min-h-[120px] flex-col gap-2 p-2.5">
                    {(byStage.get(stage) ?? []).map((o) => (
                      <OpportunityCard key={o.id} opp={o} agentId={agentId} onMove={onMove} moving={moveStage.isPending}
                        onDragStart={() => setDraggingId(o.id)} onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline/${o.id}`)} />
                    ))}
                    {(byStage.get(stage) ?? []).length === 0 && (
                      <p className="py-6 text-center text-[12px] text-slate-600">No items</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
              <h3 className="mb-3 text-[13px] font-semibold text-white">Rejected &amp; Push Failed</h3>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {TERMINAL_STAGES.flatMap((stage) => byStage.get(stage) ?? []).map((o) => (
                  <OpportunityCard key={o.id} opp={o} agentId={agentId} onMove={onMove} moving={moveStage.isPending}
                    onDragStart={() => setDraggingId(o.id)} onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline/${o.id}`)} />
                ))}
                {TERMINAL_STAGES.flatMap((stage) => byStage.get(stage) ?? []).length === 0 && (
                  <p className="text-[12px] text-slate-600">Nothing rejected or failed to push.</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-white/[0.06]">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Buyer</th>
                  <th className="px-4 py-3">Value</th>
                  <th className="px-4 py-3">Score</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3">Deadline</th>
                </tr>
              </thead>
              <tbody>
                {opps.map((o) => (
                  <tr key={o.id} tabIndex={0} role="button"
                    onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline/${o.id}`)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(`/studio/${agentId}/sales-intelligence/pipeline/${o.id}`); } }}
                    className="cursor-pointer border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400/60">
                    <td className="max-w-[320px] truncate px-4 py-3 text-white">{o.title}</td>
                    <td className="px-4 py-3 text-slate-400">{sourceLabel(o.sourceKey)}</td>
                    <td className="px-4 py-3 text-slate-400">{o.buyer ?? "\u2014"}</td>
                    <td className="px-4 py-3 font-medium text-emerald-400">{formatMoney(o.estimatedValue, o.currency)}</td>
                    <td className="px-4 py-3">
                      {o.qualificationScore != null ? (
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${scoreBadgeClass(o.qualificationScore)}`}>
                          {o.qualificationScore}/100
                        </span>
                      ) : <span className="text-slate-600">{"\u2014"}</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${stageBadgeClass(o.stage)}`}>
                        {STAGE_LABELS[o.stage] ?? humanize(o.stage)}
                      </span>
                    </td>
                    <td className={cn("px-4 py-3", deadlineUrgencyClass(o.deadlineAt))}>{formatDate(o.deadlineAt)}</td>
                  </tr>
                ))}
                {opps.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">No opportunities yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </CockpitShell>
  );
}

function OpportunityCard({ opp, onDragStart, onClick, onMove, moving }: {
  opp: SalesOpportunity; agentId: string; onDragStart: () => void; onClick: () => void;
  onMove: (id: number, stage: OpportunityStage) => void; moving: boolean;
}) {
  return (
    <div draggable onDragStart={onDragStart}
      className="flex flex-col gap-2 rounded-lg border border-white/[0.07] bg-white/[0.02] p-3 transition-colors hover:border-indigo-500/30 hover:bg-white/[0.04]">
      <button type="button" onClick={onClick}
        className="flex flex-col gap-2 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
        <div className="flex items-start gap-2">
          <GripVertical aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 cursor-grab text-slate-600" />
          <p className="line-clamp-2 text-[13px] font-medium leading-snug text-white">{opp.title}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 pl-5">
          <span className="rounded-full border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-300">
            {sourceLabel(opp.sourceKey)}
          </span>
          <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${stageBadgeClass(opp.stage)}`}>
            {STAGE_LABELS[opp.stage] ?? humanize(opp.stage)}
          </span>
          {opp.qualificationScore != null && (
            <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold ${scoreBadgeClass(opp.qualificationScore)}`}>
              {opp.qualificationScore}/100
            </span>
          )}
        </div>
        <p className="truncate pl-5 text-[11px] text-slate-400">{opp.buyer ?? "\u2014"}</p>
        <div className="flex items-center justify-between gap-2 pl-5">
          {opp.estimatedValue != null
            ? <span className="text-[12px] font-semibold text-emerald-400">{formatMoney(opp.estimatedValue, opp.currency)}</span>
            : <span className="text-[12px] text-slate-600">{"\u2014"}</span>}
          {opp.deadlineAt && (
            <span className={cn("flex items-center gap-1 text-[11px] font-medium", deadlineUrgencyClass(opp.deadlineAt))}>
              <CalendarClock className="size-3" /> {deadlineLabel(opp.deadlineAt)}
            </span>
          )}
        </div>
      </button>
      {/* Keyboard/screen-reader-accessible alternative to drag-and-drop: dispatches the same
          stage-change mutation the board uses. */}
      <div className="flex items-center gap-1.5 pl-5">
        <label htmlFor={`move-opp-${opp.id}`} className="text-[10px] uppercase tracking-wider text-slate-500">Move to</label>
        <select id={`move-opp-${opp.id}`} value="" disabled={moving}
          aria-label={`Move ${opp.title} to another stage`}
          onChange={(e) => { const stage = e.target.value as OpportunityStage; if (stage) onMove(opp.id, stage); }}
          className="min-w-0 flex-1 rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-1 text-[11px] text-slate-300 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/40 disabled:opacity-50">
          <option value="" disabled>Select stage…</option>
          {MOVE_TARGETS.filter((s) => s !== opp.stage).map((s) => (
            <option key={s} value={s} className="bg-[#0b0e16] text-slate-200">{STAGE_LABELS[s]}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
