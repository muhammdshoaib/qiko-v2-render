"use client";

import { useMemo, useState, type ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, CalendarClock, ChevronLeft, ChevronRight, GripVertical, Plus, RotateCcw, Search } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  listAgents, listSalesOpportunities, pushOpportunityToSalesforce, restoreSalesOpportunity,
  transitionSalesOpportunity, type OpportunityStage, type SalesOpportunity,
} from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import { Select } from "@/components/cockpit/controls";
import {
  deadlineLabel, deadlineUrgencyClass, formatDate, formatMoney, humanize, scoreBadgeClass,
  sourceLabel, stageBadgeClass, STAGE_LABELS,
} from "@/components/sales-intelligence/utils";

const KANBAN_COLUMNS: OpportunityStage[] = ["ingested", "qualifying", "qualified", "validated", "pushed"];
const TERMINAL_STAGES: OpportunityStage[] = ["rejected", "push_failed"];
// Stages a card can be moved to via the keyboard-accessible "Move to…" control (mirrors the
// drag-and-drop board columns so keyboard/screen-reader users have the same reach). `push_failed`
// is a Salesforce-driven system state, not a manual target, so it is excluded. Moving to `pushed`
// routes through the real push-to-salesforce action; the rest use the stage-transition endpoint.
const MOVE_TARGETS: OpportunityStage[] = [...KANBAN_COLUMNS, "rejected"];

// Rejected & failed rail: client-side tab filter + search + pagination (Staging parity).
const REJECTED_PAGE_SIZE = 6;
type RejectedFilter = "all" | "rejected" | "push_failed";

export default function SalesIntelligencePipelinePage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [view, setView] = useState<"pipeline" | "list" | "archived">("pipeline");
  const [draggingId, setDraggingId] = useState<number | null>(null);

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const oppsQ = useQuery({ queryKey: ["sales-opportunities", agentId], queryFn: () => listSalesOpportunities(agentId, { limit: "all" }), retry: false });
  const opps: SalesOpportunity[] = oppsQ.data?.opportunities ?? [];

  // Archived view: fetched on demand via the existing archived_only filter (limit=all).
  const archivedQ = useQuery({
    queryKey: ["sales-opportunities-archived", agentId],
    queryFn: () => listSalesOpportunities(agentId, { limit: "all", archived_only: true }),
    enabled: view === "archived", retry: false,
  });
  const archivedOpps: SalesOpportunity[] = archivedQ.data?.opportunities ?? [];

  const restore = useMutation({
    mutationFn: (id: number) => restoreSalesOpportunity(agentId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales-opportunities-archived", agentId] });
      qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] });
    },
  });

  // Moving to `pushed` goes through the real Salesforce push; every other target is a manual
  // stage transition. Both invalidate the same list query.
  const moveStage = useMutation({
    mutationFn: (vars: { id: number; stage: OpportunityStage }) =>
      vars.stage === "pushed"
        ? pushOpportunityToSalesforce(agentId, vars.id)
        : transitionSalesOpportunity(agentId, vars.id, vars.stage),
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
          { value: formatDate(metrics.lastScan, true), label: "Last Portal Scan", caption: metrics.sources.join(" \u00b7 ") || "-", trend: "up" },
        ]} />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex rounded-lg border border-border bg-muted/50 p-0.5">
            {(["pipeline", "list", "archived"] as const).map((v) => (
              <button key={v} onClick={() => setView(v)}
                aria-pressed={view === v}
                className={cn("rounded-md px-3.5 py-1.5 text-[13px] font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                  view === v ? "bg-indigo-50 text-indigo-800" : "text-slate-500 hover:text-foreground")}>
                {v}
              </button>
            ))}
          </div>
          <button onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline/new`)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
            <Plus className="size-3.5" /> Add opportunity
          </button>
        </div>

        {view !== "archived" && oppsQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {view !== "archived" && oppsQ.isError && <p className="text-sm text-red-400">Couldn&apos;t load the pipeline. Try refreshing.</p>}

        {view === "archived" ? (
          <ArchivedTable opps={archivedOpps} agentId={agentId} loading={archivedQ.isLoading} error={archivedQ.isError}
            onRestore={(id) => restore.mutate(id)} restoringId={restore.isPending ? (restore.variables ?? null) : null} />
        ) : view === "pipeline" ? (
          <div className="space-y-6">
            <div className="flex gap-4 overflow-x-auto pb-2">
              {KANBAN_COLUMNS.map((stage) => (
                <div key={stage} onDragOver={(e) => e.preventDefault()} onDrop={() => onDrop(stage)}
                  className="flex w-[260px] shrink-0 flex-col rounded-xl border border-border bg-white/[0.01]">
                  <div className="flex items-center justify-between border-b border-border px-3.5 py-3">
                    <span className="text-[13px] font-semibold text-foreground">{STAGE_LABELS[stage]}</span>
                    <span className="flex size-5 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-slate-600">
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

            <RejectedRail
              items={TERMINAL_STAGES.flatMap((stage) => byStage.get(stage) ?? [])}
              renderCard={(o) => (
                <OpportunityCard key={o.id} opp={o} agentId={agentId} onMove={onMove} moving={moveStage.isPending}
                  onDragStart={() => setDraggingId(o.id)} onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline/${o.id}`)} />
              )} />
          </div>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-border">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wider text-slate-500">
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
                    className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-300">
                    <td className="max-w-[320px] truncate px-4 py-3 text-foreground">{o.title}</td>
                    <td className="px-4 py-3 text-slate-400">{sourceLabel(o.sourceKey)}</td>
                    <td className="px-4 py-3 text-slate-400">{o.buyer ?? "-"}</td>
                    <td className="px-4 py-3 font-medium text-emerald-700">{formatMoney(o.estimatedValue, o.currency)}</td>
                    <td className="px-4 py-3">
                      {o.qualificationScore != null ? (
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${scoreBadgeClass(o.qualificationScore)}`}>
                          {o.qualificationScore}/100
                        </span>
                      ) : <span className="text-slate-600">{"-"}</span>}
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

// Rejected & failed rail with a tab filter, client-side search and pagination. Mirrors the
// deployed Staging behavior: the full opportunity list is already loaded, so this section
// narrows the terminal-stage cards entirely on the client.
function RejectedRail({ items, renderCard }: {
  items: SalesOpportunity[]; renderCard: (opp: SalesOpportunity) => ReactNode;
}) {
  const [filter, setFilter] = useState<RejectedFilter>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const rejectedCount = items.filter((o) => o.stage === "rejected").length;
  const failedCount = items.filter((o) => o.stage === "push_failed").length;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((o) => {
      if (filter === "rejected" && o.stage !== "rejected") return false;
      if (filter === "push_failed" && o.stage !== "push_failed") return false;
      if (!q) return true;
      return (o.title ?? "").toLowerCase().includes(q)
        || (o.buyer ?? "").toLowerCase().includes(q)
        || (o.source ?? "").toLowerCase().includes(q)
        || sourceLabel(o.sourceKey).toLowerCase().includes(q);
    });
  }, [items, filter, query]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / REJECTED_PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = filtered.slice(safePage * REJECTED_PAGE_SIZE, safePage * REJECTED_PAGE_SIZE + REJECTED_PAGE_SIZE);
  const rangeStart = filtered.length === 0 ? 0 : safePage * REJECTED_PAGE_SIZE + 1;
  const rangeEnd = Math.min(filtered.length, (safePage + 1) * REJECTED_PAGE_SIZE);

  const tabs = [
    { id: "all" as const, label: "All", count: items.length },
    { id: "rejected" as const, label: "Rejected", count: rejectedCount },
    { id: "push_failed" as const, label: "Push failed", count: failedCount },
  ];

  return (
    <div className="rounded-2xl border border-border bg-muted/40 p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold text-foreground">Rejected &amp; Push Failed</h3>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-border bg-muted/50 p-0.5" role="tablist" aria-label="Filter rejected and push failed">
            {tabs.map((tab) => (
              <button key={tab.id} type="button" role="tab" aria-selected={filter === tab.id}
                onClick={() => { setFilter(tab.id); setPage(0); }}
                className={cn("inline-flex min-h-11 items-center rounded-md px-3 py-1 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                  filter === tab.id ? "bg-indigo-50 text-indigo-800" : "text-slate-500 hover:text-foreground")}>
                {tab.label} <span className="text-slate-500">({tab.count})</span>
              </button>
            ))}
          </div>
          <label className="relative block">
            <span className="sr-only">Search rejected and push failed opportunities</span>
            <Search aria-hidden="true" className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-500" />
            <input type="search" value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(0); }}
              placeholder="Search title, buyer or source…"
              className="min-h-11 w-56 rounded-lg border border-border bg-muted py-1.5 pl-8 pr-3 text-[12px] text-slate-700 placeholder:text-slate-600 outline-none focus:border-indigo-500/40" />
          </label>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-[12px] text-slate-600">
          {items.length === 0 ? "Nothing rejected or failed to push." : "No matches. Try another filter or clear the search."}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {pageItems.map((o) => renderCard(o))}
          </div>
          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-[11px] text-slate-500" aria-live="polite">Showing {rangeStart}&ndash;{rangeEnd} of {filtered.length}</p>
            {pageCount > 1 && (
              <div className="flex items-center gap-1.5">
                <button type="button" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={safePage === 0}
                  aria-label="Previous page"
                  className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-border bg-muted px-3 py-1 text-[12px] font-medium text-slate-700 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-40">
                  <ChevronLeft className="size-3.5" /> Prev
                </button>
                <span className="text-[11px] text-slate-500">Page {safePage + 1} of {pageCount}</span>
                <button type="button" onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={safePage >= pageCount - 1}
                  aria-label="Next page"
                  className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-border bg-muted px-3 py-1 text-[12px] font-medium text-slate-700 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-40">
                  Next <ChevronRight className="size-3.5" />
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function OpportunityCard({ opp, onDragStart, onClick, onMove, moving }: {
  opp: SalesOpportunity; agentId: string; onDragStart: () => void; onClick: () => void;
  onMove: (id: number, stage: OpportunityStage) => void; moving: boolean;
}) {
  return (
    <div draggable onDragStart={onDragStart}
      className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-muted/50 p-3 transition-colors hover:border-indigo-500/30 hover:bg-muted">
      <button type="button" onClick={onClick}
        className="flex flex-col gap-2 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
        <div className="flex items-start gap-2">
          <GripVertical aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 cursor-grab text-slate-600" />
          <p className="line-clamp-2 text-[13px] font-medium leading-snug text-foreground">{opp.title}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 pl-5">
          <span className="rounded-full border border-border bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-600">
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
        <p className="truncate pl-5 text-[11px] text-slate-400">{opp.buyer ?? "-"}</p>
        <div className="flex items-center justify-between gap-2 pl-5">
          {opp.estimatedValue != null
            ? <span className="text-[12px] font-semibold text-emerald-700">{formatMoney(opp.estimatedValue, opp.currency)}</span>
            : <span className="text-[12px] text-slate-600">{"-"}</span>}
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
        <Select id={`move-opp-${opp.id}`} value="" disabled={moving}
          wrapperClassName="min-w-0 flex-1"
          aria-label={`Move ${opp.title} to another stage`}
          onChange={(e) => { const stage = e.target.value as OpportunityStage; if (stage) onMove(opp.id, stage); }}>
          <option value="" disabled>Select stage…</option>
          {MOVE_TARGETS.filter((s) => s !== opp.stage).map((s) => (
            <option key={s} value={s}>{STAGE_LABELS[s]}</option>
          ))}
        </Select>
      </div>
    </div>
  );
}

function ArchivedTable({ opps, agentId, loading, error, onRestore, restoringId }: {
  opps: SalesOpportunity[]; agentId: string; loading: boolean; error: boolean;
  onRestore: (id: number) => void; restoringId: number | null;
}) {
  const router = useRouter();
  if (loading) return <p className="text-sm text-slate-500">Loading archived opportunities…</p>;
  if (error) return <p className="text-sm text-red-400">Couldn&apos;t load the archive. Try refreshing.</p>;
  if (opps.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-2xl border border-border bg-muted/40 px-4 py-12 text-center">
        <Archive className="size-6 text-slate-600" aria-hidden="true" />
        <p className="text-sm text-slate-400">No archived opportunities.</p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-2xl border border-border">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="border-b border-border text-[11px] uppercase tracking-wider text-slate-500">
            <th className="px-4 py-3">Title</th>
            <th className="px-4 py-3">Source</th>
            <th className="px-4 py-3">Buyer</th>
            <th className="px-4 py-3">Stage</th>
            <th className="px-4 py-3">Archived</th>
            <th className="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {opps.map((o) => (
            <tr key={o.id} className="border-b border-slate-100 last:border-0 hover:bg-muted/50">
              <td className="max-w-[320px] truncate px-4 py-3">
                <button onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline/${o.id}`)}
                  className="truncate text-left text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
                  {o.title}
                </button>
              </td>
              <td className="px-4 py-3 text-slate-400">{sourceLabel(o.sourceKey)}</td>
              <td className="px-4 py-3 text-slate-400">{o.buyer ?? "-"}</td>
              <td className="px-4 py-3">
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${stageBadgeClass(o.stage)}`}>
                  {STAGE_LABELS[o.stage] ?? humanize(o.stage)}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-400">{formatDate(o.archivedAt)}</td>
              <td className="px-4 py-3 text-right">
                <button onClick={() => onRestore(o.id)} disabled={restoringId === o.id}
                  aria-label={`Restore ${o.title}`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-1.5 text-[12px] font-semibold text-slate-700 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
                  <RotateCcw className={cn("size-3.5", restoringId === o.id && "animate-spin")} /> {restoringId === o.id ? "Restoring…" : "Restore"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
