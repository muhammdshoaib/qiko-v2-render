"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Info, RefreshCw, Unlink, XCircle } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  disconnectSalesIntelSalesforce, getSalesActivityLogs, getSalesforceStatus, listAgents, type SalesActivityLog,
} from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import { formatDate } from "@/components/sales-intelligence/utils";

function actionLabel(activityType: string): string {
  return activityType
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function ToneIcon({ tone }: { tone: string }) {
  if (tone === "success") return <span className="flex items-center gap-1.5 text-emerald-400"><CheckCircle2 className="size-3.5" /> Success</span>;
  if (tone === "error") return <span className="flex items-center gap-1.5 text-red-400"><XCircle className="size-3.5" /> Failed</span>;
  if (tone === "warning") return <span className="flex items-center gap-1.5 text-amber-400"><Info className="size-3.5" /> Warning</span>;
  return <span className="flex items-center gap-1.5 text-slate-400"><Info className="size-3.5" /> Info</span>;
}

export default function SalesforcePushLogPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const sfQ = useQuery({ queryKey: ["salesforce-status", agentId], queryFn: () => getSalesforceStatus(agentId), retry: false });
  const logsQ = useQuery({ queryKey: ["sales-activity-logs", agentId], queryFn: () => getSalesActivityLogs(agentId, { per_page: 50 }), retry: false });
  const logs: SalesActivityLog[] = logsQ.data?.logs ?? [];

  const disconnect = useMutation({
    mutationFn: () => disconnectSalesIntelSalesforce(agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["salesforce-status", agentId] }),
  });

  const successful = logs.filter((l) => l.tone === "success" && l.activityType.includes("push")).length;
  const failed = logs.filter((l) => l.tone === "error").length;
  const connected = sfQ.data?.salesforce?.connected ?? false;

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="log">
      <div className="space-y-6">
        <OutcomesStrip title="SALESFORCE PUSH LOG" tiles={[
          { value: connected ? "Connected" : "Disconnected", label: "Salesforce Status", caption: connected ? "OAuth ready" : "not connected", trend: connected ? "up" : "down" },
          { value: String(successful), label: "Successful Pushes", caption: "synced to SF", trend: "up" },
          { value: String(failed), label: "Failed Attempts", caption: failed > 0 ? "needs retry" : "none", trend: failed > 0 ? "down" : "neutral" },
        ]} />

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">SALESFORCE CONNECTION</p>
              <p className="mt-1 text-[15px] font-semibold text-white">{connected ? "Connected" : "Not Connected"}</p>
              {sfQ.data?.salesforce?.instanceUrl && (
                <a href={sfQ.data.salesforce.instanceUrl} target="_blank" rel="noreferrer" className="mt-1 block rounded text-[13px] text-indigo-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
                  {sfQ.data.salesforce.instanceUrl}
                </a>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => disconnect.mutate()} disabled={!connected || disconnect.isPending}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50">
                <Unlink className="size-3.5" /> {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
              </button>
              <button onClick={() => { sfQ.refetch(); logsQ.refetch(); }} disabled={sfQ.isFetching || logsQ.isFetching}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50">
                <RefreshCw className={cn("size-3.5", (sfQ.isFetching || logsQ.isFetching) && "animate-spin")} /> {sfQ.isFetching || logsQ.isFetching ? "Refreshing…" : "Refresh"}
              </button>
            </div>
          </div>
        </div>

        <p className="text-[12px] text-slate-500">Showing {logs.length} events from activity-logs API</p>

        <div className="overflow-x-auto rounded-2xl border border-white/[0.06]">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wider text-slate-500">
                <th className="whitespace-nowrap px-4 py-3">Status</th>
                <th className="whitespace-nowrap px-4 py-3">Action</th>
                <th className="px-4 py-3">Opportunity</th>
                <th className="whitespace-nowrap px-4 py-3">Salesforce ID</th>
                <th className="whitespace-nowrap px-4 py-3">Attempted</th>
                <th className="px-4 py-3">Detail / Error</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className="border-b border-white/[0.04] last:border-0">
                  <td className="whitespace-nowrap px-4 py-3"><ToneIcon tone={log.tone} /></td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-300">{actionLabel(log.activityType)}</td>
                  <td className={cn("max-w-[280px] truncate px-4 py-3", log.tone === "error" ? "text-red-300" : "text-slate-300")}>{log.action}</td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px] text-slate-400">
                    {(log.metadata?.salesforce_opportunity_id as string) ?? "-"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-400">{formatDate(log.createdAt)}</td>
                  <td className="max-w-[320px] truncate px-4 py-3 text-slate-500">{log.detail ?? log.action}</td>
                </tr>
              ))}
              {logsQ.isLoading && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Loading push activity{"\u2026"}</td></tr>
              )}
              {!logsQ.isLoading && logsQ.isError && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-red-300">Couldn&apos;t load the push log. Try refreshing.</td></tr>
              )}
              {!logsQ.isLoading && !logsQ.isError && logs.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No activity recorded yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </CockpitShell>
  );
}
