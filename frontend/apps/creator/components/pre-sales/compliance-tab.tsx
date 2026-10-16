"use client";

import { useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, FileText, Loader2, RefreshCw, ShieldCheck, Upload, User } from "lucide-react";
import {
  complianceCheck, getCompliance, getRfpPack, getTenderStatus,
  type ComplianceItem, type GenState,
} from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";
import { OutcomesStrip, type OutcomeTile } from "@/components/cockpit/outcomes-strip";

const IN_FLIGHT: GenState[] = ["pending", "running"];
const isInFlight = (s: GenState | undefined) => s != null && IN_FLIGHT.includes(s);

export function ComplianceTab({ packId, onOpenSources }: { packId: string; onOpenSources: () => void }) {
  const qc = useQueryClient();
  const packQ = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });
  const docText = packQ.data?.document_text ?? "";

  // Read the PERSISTED compliance result with a plain GET (no LLM) so it survives login/logout
  // instead of re-parsing the tender on every mount. Regenerate is explicit only. GET returns null
  // when nothing has been generated yet (distinct from an empty [] = generated, no items found).
  const checkQ = useQuery({
    queryKey: ["pack-compliance", packId],
    queryFn: () => getCompliance(packId),
    staleTime: Infinity,
    retry: false,
  });

  // Poll /status while the compliance check is still generating in the background, then refetch it.
  const statusQ = useQuery({
    queryKey: ["tender-status", packId],
    queryFn: () => getTenderStatus(packId),
    refetchInterval: (q) => (isInFlight(q.state.data?.compliance) ? 3000 : false),
  });
  const generating = isInFlight(statusQ.data?.compliance);

  const complianceState = statusQ.data?.compliance;
  useEffect(() => {
    if (complianceState === "ready" && checkQ.data == null) checkQ.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [complianceState]);

  const regenerate = useMutation({
    mutationFn: () => complianceCheck(packId, docText),
    onSuccess: (items) => qc.setQueryData(["pack-compliance", packId], items),
  });

  const items: ComplianceItem[] = checkQ.data ?? [];
  // Derive the 4 idg metric cards from the compliance items + the pack deadline:
  //  - Mandatory items  = every extracted pass/fail requirement
  //  - AI can address   = owner "AI" (a grounded KB narrative can answer it)
  //  - Needs IDG input  = owner "Human" (signatures / pricing / forms / financial evidence)
  //  - Deadline         = the pack's submission deadline
  const stats = useMemo(() => ({
    total: items.length,
    ai: items.filter((i) => i.owner === "AI").length,
    human: items.filter((i) => i.owner === "Human").length,
  }), [items]);

  if (packQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-muted" />)}</div>;
  }

  if (!docText.trim()) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-14 text-center">
        <span className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-muted text-slate-500">
          <ShieldCheck className="size-6" />
        </span>
        <p className="text-sm font-semibold text-foreground">No tender document yet</p>
        <p className="mt-1 max-w-sm text-[12px] text-slate-500">Upload the RFP to extract its mandatory compliance requirements.</p>
        <button onClick={onOpenSources}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
          <Upload className="size-4" /> Go to Sources
        </button>
      </div>
    );
  }

  if (checkQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-muted" />)}</div>;
  }

  // No persisted compliance yet: either it's still being generated in the background (small
  // generating state while /status is polled), or it needs an explicit generate/regenerate.
  if (checkQ.data == null) {
    if (generating || regenerate.isPending) {
      return (
        <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-14 text-center">
          <Loader2 className="mb-3 size-6 animate-spin text-indigo-400" />
          <p className="text-sm font-medium text-slate-700">Checking compliance{"\u2026"}</p>
          <p className="mt-1 text-[12px] text-slate-500">Extracting mandatory pass/fail requirements from the tender.</p>
        </div>
      );
    }
    return (
      <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-12 text-center">
        {regenerate.isError ? <AlertTriangle className="mb-3 size-6 text-amber-700" /> : <ShieldCheck className="mb-3 size-6 text-slate-500" />}
        <p className="text-sm font-medium text-slate-700">
          {regenerate.isError ? "Couldn't run the compliance check" : "No compliance check yet"}
        </p>
        <button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
          <RefreshCw className="size-4" /> Run compliance check
        </button>
      </div>
    );
  }

  const tiles: OutcomeTile[] = [
    { value: String(stats.total), label: "Mandatory items", caption: "pass/fail" },
    { value: String(stats.ai), label: "AI can address", caption: "from KB", trend: "up" },
    { value: String(stats.human), label: "Needs IDG input", caption: "forms/signatures/pricing" },
    { value: formatShortDate(packQ.data?.deadline), label: "Deadline", caption: "submission" },
  ];

  return (
    <div className="space-y-6">
      <OutcomesStrip title="COMPLIANCE" tiles={tiles} />

      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-[15px] font-semibold text-foreground">
            <ShieldCheck className="size-4 text-indigo-400" /> Compliance Checker
          </h2>
          <p className="mt-1 max-w-2xl text-[13px] text-slate-400">
            Mandatory requirements and disqualifiers extracted from the tender, tagged by who must action
            each so nothing that could disqualify the bid is missed.
          </p>
        </div>
        <button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}
          aria-label="Regenerate the compliance check"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-muted px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
          {regenerate.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Regenerate
        </button>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-12 text-center">
          <FileText className="mb-3 size-6 text-slate-500" />
          <p className="text-sm font-medium text-slate-600">No compliance requirements found</p>
          <p className="mt-1 text-[12px] text-slate-500">The tender didn&apos;t list explicit mandatory pass/fail items.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-border">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3">Requirement</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Owner</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="border-b border-slate-100 align-top last:border-0">
                  <td className="max-w-[520px] px-4 py-3 text-slate-700">
                    <p>{it.requirement}</p>
                    {it.note && <p className="mt-1 text-[11px] text-slate-500">{it.note}</p>}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                      {it.category || "-"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${it.owner === "AI" ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-600" : "border-amber-500/30 bg-amber-50 text-amber-700"}`}>
                      {it.owner === "AI" ? <Bot className="size-3" /> : <User className="size-3" />}
                      {it.owner === "AI" ? "AI draft" : "IDG input"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
