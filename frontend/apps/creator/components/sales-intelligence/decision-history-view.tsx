"use client";

// Decision History -- ported from qiko-frontend origin/idg-sales DecisionHistoryView.tsx, adapted
// to the V2 cockpit style. Shows the approve/reject/override audit trail for one opportunity
// (who decided what and when), read from GET /opportunities/{id}/decisions.
import { useQuery } from "@tanstack/react-query";
import { Check, HelpCircle, History, X } from "lucide-react";
import { getSalesOpportunityDecisions, type SalesDecision } from "@/lib/api";
import { formatDate } from "@/components/sales-intelligence/utils";

function decisionBadgeClass(decision: string | null): string {
  if (decision === "approved") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (decision === "rejected") return "border-red-500/30 bg-red-500/10 text-red-400";
  return "border-amber-500/30 bg-amber-500/10 text-amber-400";
}

function DecisionIcon({ decision }: { decision: string | null }) {
  if (decision === "approved") return <Check className="size-3.5" />;
  if (decision === "rejected") return <X className="size-3.5" />;
  return <HelpCircle className="size-3.5" />;
}

export function DecisionHistoryView({ agentId, opportunityId }: { agentId: string; opportunityId: string }) {
  const q = useQuery({
    queryKey: ["sales-decisions", agentId, opportunityId],
    queryFn: () => getSalesOpportunityDecisions(agentId, opportunityId),
    retry: false,
  });
  const decisions: SalesDecision[] = q.data?.decisions ?? [];

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <div className="flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
          <History className="size-4" />
        </span>
        <p className="text-[13px] font-semibold text-white">Decision History</p>
      </div>

      {q.isLoading ? (
        <p className="mt-4 text-[13px] text-slate-500">{"Loading\u2026"}</p>
      ) : decisions.length === 0 ? (
        <p className="mt-4 text-[13px] text-slate-500">No review decisions recorded yet.</p>
      ) : (
        <ol className="mt-4 space-y-3">
          {decisions.map((d) => (
            <li key={d.id} className="flex items-start gap-3 border-l-2 border-white/[0.08] pl-3">
              <span className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border ${decisionBadgeClass(d.decision)}`}>
                <DecisionIcon decision={d.decision} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${decisionBadgeClass(d.decision)}`}>
                    {d.decisionLabel}
                  </span>
                  <span className="text-[11px] text-slate-500">{formatDate(d.createdAt, true)}</span>
                </div>
                {d.detail && <p className="mt-1 text-[13px] text-slate-300">{d.detail}</p>}
                {d.reviewerUserId && <p className="mt-0.5 text-[11px] text-slate-500">Reviewer: {d.reviewerUserId}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
