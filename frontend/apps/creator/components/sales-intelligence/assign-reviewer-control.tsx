"use client";

// Assign Reviewer -- ported from qiko-frontend origin/idg-sales AssignReviewerControl.tsx, adapted
// to the V2 cockpit style. The V2 teams module isn't enumerable per-tenant yet, so this uses a
// free-text reviewer name (+ optional user id) rather than a team-member <select>; the backend
// stores assigned_reviewer_user_id / assigned_reviewer_name / assigned_at and activity-logs the
// change (audit trail). Editor role required (enforced server-side).
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, UserCheck, X } from "lucide-react";
import { assignSalesReviewer, type SalesOpportunity } from "@/lib/api";
import { Input } from "@/components/cockpit/controls";
import { formatDate } from "@/components/sales-intelligence/utils";

export function AssignReviewerControl({ agentId, opp, onSaved }: {
  agentId: string; opp: SalesOpportunity; onSaved?: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(opp.assignedReviewerName ?? "");
  const [userId, setUserId] = useState(opp.assignedReviewerUserId ?? "");

  useEffect(() => {
    setName(opp.assignedReviewerName ?? "");
    setUserId(opp.assignedReviewerUserId ?? "");
  }, [opp.id, opp.assignedReviewerName, opp.assignedReviewerUserId]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["sales-opportunity", agentId, opp.id] });
    qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] });
    onSaved?.();
  };
  const assign = useMutation({
    mutationFn: (body: { user_id: string | null; name: string | null }) =>
      assignSalesReviewer(agentId, opp.id, body),
    onSuccess: invalidate,
  });

  const trimmedName = name.trim();
  const trimmedId = userId.trim();
  const dirty = trimmedName !== (opp.assignedReviewerName ?? "") || trimmedId !== (opp.assignedReviewerUserId ?? "");
  const hasReviewer = Boolean(opp.assignedReviewerName || opp.assignedReviewerUserId);

  return (
    <div className="rounded-2xl border border-border bg-muted/40 p-5">
      <div className="flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
          <UserCheck className="size-4" />
        </span>
        <div>
          <p className="text-[13px] font-semibold text-foreground">Reviewer</p>
          <p className="text-[11px] text-slate-500">
            {hasReviewer
              ? `${opp.assignedReviewerName || opp.assignedReviewerUserId}${opp.assignedAt ? ` \u00b7 assigned ${formatDate(opp.assignedAt)}` : ""}`
              : "Unassigned"}
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={`reviewer-name-${opp.id}`} className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Reviewer name</label>
          <Input id={`reviewer-name-${opp.id}`} value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Alice Ahmed" className="mt-1.5" />
        </div>
        <div>
          <label htmlFor={`reviewer-uid-${opp.id}`} className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500">User ID (optional)</label>
          <Input id={`reviewer-uid-${opp.id}`} value={userId} onChange={(e) => setUserId(e.target.value)}
            placeholder="team member user id" className="mt-1.5" />
        </div>
      </div>

      <div className="mt-4 flex items-center justify-end gap-2">
        {hasReviewer && (
          <button onClick={() => assign.mutate({ user_id: null, name: null })} disabled={assign.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-2 text-[13px] font-medium text-slate-600 hover:bg-muted disabled:opacity-50">
            <X className="size-3.5" /> Clear
          </button>
        )}
        <button
          onClick={() => assign.mutate({ user_id: trimmedId || null, name: trimmedName || null })}
          disabled={assign.isPending || !dirty || (!trimmedName && !trimmedId)}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-500 px-4 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 disabled:opacity-50">
          {assign.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <UserCheck className="size-3.5" />}
          {assign.isPending ? "Saving\u2026" : "Assign reviewer"}
        </button>
      </div>
    </div>
  );
}
