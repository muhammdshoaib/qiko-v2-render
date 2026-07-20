"use client";

// Agent-level Decision History -- ported from qiko-frontend origin/idg-sales DecisionHistoryView.tsx,
// adapted to the V2 cockpit. Aggregates every approve/reject/override decision across ALL of the
// agent's opportunities (GET /sales-intelligence/{id}/decision-history) with decision + reviewer
// filters, a refresh, a skeleton loader, empty/error states and CSV export. This is the standalone
// audit page; the per-opportunity embed stays in components/sales-intelligence/decision-history-view.
import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Check, Download, Gavel, HelpCircle, History, RefreshCw, X } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  getSalesDecisionHistory, listAgents,
  type SalesDecisionFilter, type SalesDecisionHistoryEntry,
} from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import { formatDate, humanize } from "@/components/sales-intelligence/utils";

const DECISION_FILTERS: { id: SalesDecisionFilter; label: string }[] = [
  { id: "all", label: "All decisions" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
  { id: "override", label: "Override" },
];

function decisionBadgeClass(decision: string | null): string {
  if (decision === "approved") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (decision === "rejected") return "border-red-500/30 bg-red-500/10 text-red-400";
  if (decision === "needs_review") return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  return "border-slate-500/30 bg-slate-500/10 text-slate-400";
}

function DecisionIcon({ decision }: { decision: string | null }) {
  if (decision === "approved") return <Check className="size-3.5" />;
  if (decision === "rejected") return <X className="size-3.5" />;
  if (decision === "needs_review") return <HelpCircle className="size-3.5" />;
  return <History className="size-3.5" />;
}

function reviewerName(entry: SalesDecisionHistoryEntry): string {
  return entry.reviewer?.userName || entry.reviewer?.email
    || (entry.reviewerUserId ? `User ${entry.reviewerUserId}` : "System");
}

function csvEscape(value: unknown): string {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(filename: string, rows: SalesDecisionHistoryEntry[]): void {
  const header = ["id", "decision", "opportunityId", "opportunityTitle", "opportunityStage", "reviewer", "detail", "createdAt"];
  const lines = [
    header.join(","),
    ...rows.map((row) => [
      row.id, row.decision ?? "", row.opportunityId ?? "", row.opportunityTitle ?? "",
      row.opportunityStage ?? "", reviewerName(row), row.detail ?? "", row.createdAt ?? "",
    ].map(csvEscape).join(",")),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function DecisionHistorySkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/[0.06]" aria-busy="true" aria-label="Loading decision history">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-6 border-b border-white/[0.04] px-4 py-4 last:border-0">
          <div className="h-3.5 w-20 animate-pulse rounded bg-white/[0.06]" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3.5 w-48 max-w-full animate-pulse rounded bg-white/[0.06]" />
            <div className="h-3 w-24 animate-pulse rounded bg-white/[0.06]" />
          </div>
          <div className="h-3.5 w-28 animate-pulse rounded bg-white/[0.06]" />
          <div className="h-3.5 w-28 animate-pulse rounded bg-white/[0.06]" />
          <div className="h-3.5 w-40 flex-1 animate-pulse rounded bg-white/[0.06]" />
        </div>
      ))}
    </div>
  );
}

export default function SalesDecisionHistoryPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const [decision, setDecision] = useState<SalesDecisionFilter>("all");
  const [reviewerUserId, setReviewerUserId] = useState("");

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const q = useQuery({
    queryKey: ["sales-decision-history", agentId, decision, reviewerUserId],
    queryFn: () => getSalesDecisionHistory(agentId, {
      ...(decision !== "all" ? { decision } : {}),
      ...(reviewerUserId !== "" ? { reviewer_user_id: reviewerUserId } : {}),
    }),
    retry: false,
  });

  const entries = useMemo(() => q.data?.decisionHistory ?? [], [q.data]);
  const reviewers = q.data?.reviewers ?? [];
  const summary = q.data?.summary ?? { approved: 0, rejected: 0, overrides: 0, total: 0 };

  const handleDownload = () => {
    if (entries.length === 0) return;
    const stamp = new Date().toISOString().slice(0, 10);
    const scope = reviewerUserId ? `reviewer-${reviewerUserId}` : "all";
    downloadCsv(`decision-history-${scope}-${stamp}.csv`, entries);
  };

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="decision-history">
      <div className="space-y-6">
        <OutcomesStrip title="DECISION HISTORY" tiles={[
          { value: String(summary.approved), label: "Approved", caption: "validated", trend: "up" },
          { value: String(summary.rejected), label: "Rejected", caption: "out of scope", trend: "down" },
          { value: String(summary.overrides), label: "Overrides", caption: "sent back for review", trend: "neutral" },
          { value: String(summary.total), label: "Total Decisions", caption: "shown", trend: "neutral" },
        ]} />

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2.5">
              <span className="mt-0.5 flex size-8 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
                <Gavel className="size-4" />
              </span>
              <div>
                <p className="text-[15px] font-semibold text-white">Decision History</p>
                <p className="mt-1 max-w-xl text-[13px] text-slate-400">
                  Every approval, rejection and override recorded across this agent&apos;s opportunities, for audit.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={handleDownload} disabled={q.isLoading || entries.length === 0}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50">
                <Download className="size-3.5" /> Download {reviewerUserId ? "selected" : "all"}
              </button>
              <button onClick={() => q.refetch()} disabled={q.isFetching}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50">
                <RefreshCw className={cn("size-3.5", q.isFetching && "animate-spin")} /> {q.isFetching ? "Refreshing\u2026" : "Refresh"}
              </button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {DECISION_FILTERS.map((f) => (
              <button key={f.id} onClick={() => setDecision(f.id)}
                aria-pressed={decision === f.id}
                className={cn("rounded-lg px-2.5 py-1.5 text-[12px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                  decision === f.id
                    ? "border border-indigo-500/30 bg-indigo-500/10 text-indigo-200"
                    : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200")}>
                {f.label}
              </button>
            ))}
            <select value={reviewerUserId} onChange={(e) => setReviewerUserId(e.target.value)}
              aria-label="Filter by reviewer"
              className="ml-1 rounded-lg border border-white/10 bg-[#0a0f1a] px-2.5 py-1.5 text-[12px] text-slate-200 outline-none focus-visible:border-indigo-400/50 focus-visible:ring-2 focus-visible:ring-indigo-400/40">
              <option value="">All reviewers</option>
              {reviewers.map((r) => (
                <option key={r.id} value={r.id}>{r.userName || r.email || `User ${r.id}`}</option>
              ))}
            </select>
          </div>
        </div>

        {q.isLoading ? (
          <DecisionHistorySkeleton />
        ) : q.isError ? (
          <div className="rounded-2xl border border-red-500/20 bg-red-500/5 px-6 py-10 text-center">
            <p className="text-[14px] font-semibold text-red-200">Couldn&apos;t load decision history</p>
            <p className="mt-2 text-[13px] text-red-300/80">Please try refreshing.</p>
            <button onClick={() => q.refetch()}
              className="mt-4 rounded-lg bg-indigo-500 px-4 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
              Retry
            </button>
          </div>
        ) : entries.length === 0 ? (
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] px-6 py-12 text-center">
            <span className="mx-auto flex size-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400">
              <Gavel className="size-5" />
            </span>
            <p className="mt-3 text-[14px] font-semibold text-white">No decisions recorded yet</p>
            <p className="mt-1 text-[13px] text-slate-500">
              Approve, reject, or send opportunities back for review to populate this audit trail.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-white/[0.06]">
            <table className="w-full min-w-[860px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3">Decision</th>
                  <th className="px-4 py-3">Opportunity</th>
                  <th className="px-4 py-3">Reviewer</th>
                  <th className="whitespace-nowrap px-4 py-3">When</th>
                  <th className="px-4 py-3">Detail</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02]">
                    <td className="px-4 py-3">
                      <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold", decisionBadgeClass(entry.decision))}>
                        <DecisionIcon decision={entry.decision} /> {entry.decisionLabel}
                      </span>
                    </td>
                    <td className="max-w-[260px] px-4 py-3">
                      <p className="truncate text-slate-200">
                        {entry.opportunityTitle || (entry.opportunityId ? `Opportunity ${entry.opportunityId}` : "-")}
                      </p>
                      {entry.opportunityStage && (
                        <p className="mt-0.5 text-[10px] text-slate-500">{humanize(entry.opportunityStage)}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-[12px] text-slate-200">{reviewerName(entry)}</p>
                      {entry.reviewer?.email && entry.reviewer?.userName && (
                        <p className="text-[10px] text-slate-500">{entry.reviewer.email}</p>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-400">{formatDate(entry.createdAt, true)}</td>
                    <td className="max-w-[320px] px-4 py-3">
                      <p className="truncate text-slate-500" title={entry.detail ?? ""}>{entry.detail || "-"}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </CockpitShell>
  );
}
