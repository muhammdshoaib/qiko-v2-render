"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@qiko/ui";
import { getSalesScanHistory, listAgents, type SalesScanHistoryEntry } from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import { formatDate, sourceLabel } from "@/components/sales-intelligence/utils";

const SOURCE_FILTERS = [
  { id: "all", label: "All sources" },
  { id: "ted", label: "TED" },
  { id: "ungm", label: "UNGM" },
] as const;
const STATUS_FILTERS = [
  { id: "all", label: "All status" },
  { id: "success", label: "Success" },
  { id: "failed", label: "Failed" },
] as const;
type SourceFilter = (typeof SOURCE_FILTERS)[number]["id"];
type StatusFilter = (typeof STATUS_FILTERS)[number]["id"];

function StatusCell({ status }: { status: string }) {
  if (status === "success") return <span className="flex items-center gap-1.5 text-emerald-700"><CheckCircle2 className="size-3.5" /> Success</span>;
  if (status === "failed") return <span className="flex items-center gap-1.5 text-red-400"><XCircle className="size-3.5" /> Failed</span>;
  return <span className="text-slate-400">{status || "-"}</span>;
}

function FilterTabs<T extends string>({ label, options, value, onChange }: {
  label: string; options: readonly { id: T; label: string }[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-border bg-muted/50 p-0.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" aria-pressed={value === o.id} onClick={() => onChange(o.id)}
          className={cn("inline-flex min-h-11 min-w-11 items-center justify-center rounded-md px-3 py-1 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
            value === o.id ? "bg-indigo-50 text-indigo-800" : "text-slate-500 hover:text-foreground")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function SalesScanHistoryPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const historyQ = useQuery({
    queryKey: ["sales-scan-history", agentId, sourceFilter, statusFilter],
    queryFn: () => getSalesScanHistory(agentId, {
      ...(sourceFilter !== "all" ? { source_key: sourceFilter } : {}),
      ...(statusFilter !== "all" ? { status: statusFilter } : {}),
      limit: 100,
    }),
    retry: false,
  });
  const entries: SalesScanHistoryEntry[] = historyQ.data?.history ?? [];
  const successCount = entries.filter((e) => e.status === "success").length;
  const failedCount = entries.filter((e) => e.status === "failed").length;

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="scan-history">
      <div className="space-y-6">
        <OutcomesStrip title="SCAN HISTORY" tiles={[
          { value: String(entries.length), label: "Scans Shown", caption: "most recent 100", trend: "up" },
          { value: String(successCount), label: "Successful", caption: "completed scans", trend: "up" },
          { value: String(failedCount), label: "Failed", caption: "scan errors", trend: failedCount > 0 ? "down" : "neutral" },
        ]} />

        <div className="flex flex-wrap items-center gap-3">
          <FilterTabs label="Filter by source" options={SOURCE_FILTERS} value={sourceFilter} onChange={setSourceFilter} />
          <FilterTabs label="Filter by status" options={STATUS_FILTERS} value={statusFilter} onChange={setStatusFilter} />
        </div>

        {historyQ.isLoading && <p className="text-sm text-slate-500">Loading scan history…</p>}
        {historyQ.isError && <p className="text-sm text-red-400">Couldn&apos;t load scan history. Try refreshing.</p>}

        {!historyQ.isLoading && !historyQ.isError && (
          <div className="overflow-x-auto rounded-2xl border border-border">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wider text-slate-500">
                  <th scope="col" className="px-4 py-3">Source</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3">Found</th>
                  <th scope="col" className="px-4 py-3">Started</th>
                  <th scope="col" className="px-4 py-3">Finished</th>
                  <th scope="col" className="px-4 py-3">Error</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-b border-slate-100 last:border-0 hover:bg-muted/50">
                    <td className="px-4 py-3 text-slate-600">{sourceLabel(e.sourceKey)}</td>
                    <td className="px-4 py-3"><StatusCell status={e.status} /></td>
                    <td className="px-4 py-3 text-slate-600">{e.opportunitiesFound}</td>
                    <td className="px-4 py-3 text-slate-400">{formatDate(e.startedAt, true)}</td>
                    <td className="px-4 py-3 text-slate-400">{formatDate(e.finishedAt, true)}</td>
                    <td className="max-w-[280px] truncate px-4 py-3 text-red-300/80" title={e.error ?? undefined}>{e.error ?? "-"}</td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No scans match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </CockpitShell>
  );
}
