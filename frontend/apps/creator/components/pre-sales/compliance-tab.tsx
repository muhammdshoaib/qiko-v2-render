"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, FileText, Loader2, ShieldCheck, Upload, User } from "lucide-react";
import { complianceCheck, getRfpPack, type ComplianceItem } from "@/lib/api";

export function ComplianceTab({ packId, onOpenSources }: { packId: string; onOpenSources: () => void }) {
  const packQ = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });
  const docText = packQ.data?.document_text ?? "";

  const checkQ = useQuery({
    queryKey: ["pack-compliance", packId],
    queryFn: () => complianceCheck(packId, docText),
    enabled: !!docText.trim(),
    staleTime: Infinity,
    retry: false,
  });

  const items: ComplianceItem[] = checkQ.data ?? [];
  const stats = useMemo(() => ({
    total: items.length,
    mandatory: items.filter((i) => i.mandatory).length,
    ai: items.filter((i) => i.owner === "AI").length,
    human: items.filter((i) => i.owner === "Human").length,
  }), [items]);

  if (packQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-white/[0.04]" />)}</div>;
  }

  if (!docText.trim()) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
        <span className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-white/[0.04] text-slate-500">
          <ShieldCheck className="size-6" />
        </span>
        <p className="text-sm font-semibold text-white">No tender document yet</p>
        <p className="mt-1 max-w-sm text-[12px] text-slate-500">Upload the RFP to extract its mandatory compliance requirements.</p>
        <button onClick={onOpenSources}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
          <Upload className="size-4" /> Go to Sources
        </button>
      </div>
    );
  }

  if (checkQ.isLoading) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
        <Loader2 className="mb-3 size-6 animate-spin text-indigo-400" />
        <p className="text-sm font-medium text-slate-200">Checking compliance{"\u2026"}</p>
        <p className="mt-1 text-[12px] text-slate-500">Extracting mandatory pass/fail requirements from the tender.</p>
      </div>
    );
  }

  if (checkQ.isError) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-red-500/20 bg-red-500/[0.06] px-4 py-12 text-center">
        <AlertTriangle className="mb-3 size-6 text-red-400" />
        <p className="text-sm font-medium text-red-200">Couldn&apos;t run the compliance check</p>
        <button onClick={() => checkQ.refetch()}
          className="mt-4 rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-2 text-[13px] font-semibold text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: "Requirements", value: stats.total },
          { label: "Mandatory", value: stats.mandatory },
          { label: "AI-owned", value: stats.ai },
          { label: "Human-owned", value: stats.human },
        ].map((m) => (
          <div key={m.label} className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{m.label}</p>
            <p className="mt-1 text-2xl font-bold text-white">{m.value}</p>
          </div>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-12 text-center">
          <FileText className="mb-3 size-6 text-slate-500" />
          <p className="text-sm font-medium text-slate-300">No compliance requirements found</p>
          <p className="mt-1 text-[12px] text-slate-500">The tender didn&apos;t list explicit mandatory pass/fail items.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-white/[0.06]">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3">Requirement</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Owner</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="border-b border-white/[0.04] align-top last:border-0">
                  <td className="max-w-[420px] px-4 py-3 text-slate-200">
                    <p>{it.requirement}</p>
                    {it.note && <p className="mt-1 text-[11px] text-slate-500">{it.note}</p>}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{it.category || "\u2014"}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${it.mandatory ? "border-red-500/30 bg-red-500/10 text-red-400" : "border-slate-500/30 bg-slate-500/10 text-slate-400"}`}>
                      {it.mandatory ? "Mandatory" : "Optional"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${it.owner === "AI" ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-300" : "border-amber-500/30 bg-amber-500/10 text-amber-400"}`}>
                      {it.owner === "AI" ? <Bot className="size-3" /> : <User className="size-3" />} {it.owner}
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
