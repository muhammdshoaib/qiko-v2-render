"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CalendarClock, FileText, Loader2, RefreshCw, ScrollText, ShieldAlert, Target, Upload,
} from "lucide-react";
import { AnswerMarkdown } from "@/components/chat-message";
import { getBrief, getRfpPack, getTenderStatus, tenderBrief, type GenState } from "@/lib/api";

const IN_FLIGHT: GenState[] = ["pending", "running"];
const isInFlight = (s: GenState | undefined) => s != null && IN_FLIGHT.includes(s);

export function BriefTab({ packId, onOpenSources }: { packId: string; onOpenSources: () => void }) {
  const qc = useQueryClient();
  const packQ = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });
  const docText = packQ.data?.document_text ?? "";

  // The brief is generated once by the background job and PERSISTED. Read it with a plain GET so it
  // survives login/logout instead of re-running the LLM on every mount. Regenerate is explicit only.
  const briefQ = useQuery({
    queryKey: ["pack-brief", packId],
    queryFn: () => getBrief(packId),
    staleTime: Infinity,
    retry: false,
  });

  // Poll /status while the brief is still being generated in the background, then refetch it.
  const statusQ = useQuery({
    queryKey: ["tender-status", packId],
    queryFn: () => getTenderStatus(packId),
    refetchInterval: (q) => (isInFlight(q.state.data?.brief) ? 3000 : false),
  });
  const generating = isInFlight(statusQ.data?.brief);

  // When the background brief finishes (in-flight -> ready), pull the persisted result in.
  const briefState = statusQ.data?.brief;
  useEffect(() => {
    if (briefState === "ready" && !briefQ.data) briefQ.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [briefState]);

  const regenerate = useMutation({
    mutationFn: () => tenderBrief(packId, docText),
    onSuccess: (b) => qc.setQueryData(["pack-brief", packId], b),
  });

  if (packQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-muted" />)}</div>;
  }

  if (!docText.trim()) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-14 text-center">
        <span className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-muted text-slate-500">
          <FileText className="size-6" />
        </span>
        <p className="text-sm font-semibold text-foreground">No tender document yet</p>
        <p className="mt-1 max-w-sm text-[12px] text-slate-500">Upload the RFP so the AI can produce a bid-context brief.</p>
        <button onClick={onOpenSources}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
          <Upload className="size-4" /> Go to Sources
        </button>
      </div>
    );
  }

  if (briefQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-muted" />)}</div>;
  }

  const b = briefQ.data;

  // No persisted brief yet: either it's still being generated in the background (show a small
  // generating state while /status is polled), or it needs an explicit generate/regenerate.
  if (!b) {
    if (generating || regenerate.isPending) {
      return (
        <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-14 text-center">
          <Loader2 className="mb-3 size-6 animate-spin text-indigo-400" />
          <p className="text-sm font-medium text-slate-700">Analysing the tender{"\u2026"}</p>
          <p className="mt-1 text-[12px] text-slate-500">Extracting scope, format, dates, success criteria and risks.</p>
        </div>
      );
    }
    return (
      <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-12 text-center">
        {regenerate.isError ? <AlertTriangle className="mb-3 size-6 text-amber-700" /> : <ScrollText className="mb-3 size-6 text-slate-500" />}
        <p className="text-sm font-medium text-slate-700">
          {regenerate.isError ? "Couldn't generate the brief" : "No brief generated yet"}
        </p>
        <button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
          <RefreshCw className="size-4" /> Generate brief
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}
          aria-label="Regenerate the tender brief"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
          {regenerate.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Regenerate
        </button>
      </div>

      <div className="rounded-2xl border border-border bg-muted/40 p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
          <ScrollText className="size-3.5" /> Summary
        </div>
        <div className="mt-2 text-[13px] leading-relaxed text-slate-600"><AnswerMarkdown text={b.summary || "N/A"} /></div>
      </div>

      <div className="rounded-2xl border border-border bg-muted/40 p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-violet-300">
          <Target className="size-3.5" /> Scope
        </div>
        <div className="mt-2 text-[13px] leading-relaxed text-slate-600"><AnswerMarkdown text={b.scope || "N/A"} /></div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BriefList icon={<CalendarClock className="size-3.5" />} title="Key dates" tone="text-indigo-400" items={b.key_dates} />
        <BriefList icon={<Target className="size-3.5" />} title="Success criteria" tone="text-emerald-700" items={b.success_criteria} />
      </div>

      <div className="rounded-2xl border border-border bg-muted/40 p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <FileText className="size-3.5" /> Submission format
        </div>
        <div className="mt-2 text-[13px] leading-relaxed text-slate-600"><AnswerMarkdown text={b.submission_format || "N/A"} /></div>
      </div>

      <BriefList icon={<ShieldAlert className="size-3.5" />} title="Gaps & risks" tone="text-amber-700" items={b.gaps_and_risks} warn />
    </div>
  );
}

function BriefList({ icon, title, tone, items, warn }: {
  icon: React.ReactNode; title: string; tone: string; items: string[]; warn?: boolean;
}) {
  return (
    <div className={`rounded-2xl border p-5 ${warn ? "border-amber-500/15 bg-amber-500/[0.03]" : "border-border bg-muted/40"}`}>
      <div className={`flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider ${tone}`}>
        {icon} <span>{title}</span>
      </div>
      {items?.length ? (
        <ul className="mt-2.5 space-y-1.5">
          {items.map((it, i) => (
            <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-slate-600">
              <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${warn ? "bg-amber-400" : "bg-indigo-400"}`} />
              <span>{it}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[12px] text-slate-500">None identified.</p>
      )}
    </div>
  );
}
