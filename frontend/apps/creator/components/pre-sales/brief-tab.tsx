"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, CalendarClock, FileText, Loader2, ScrollText, ShieldAlert, Target, Upload,
} from "lucide-react";
import { AnswerMarkdown } from "@/components/chat-message";
import { getRfpPack, tenderBrief } from "@/lib/api";

export function BriefTab({ packId, onOpenSources }: { packId: string; onOpenSources: () => void }) {
  const packQ = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });
  const docText = packQ.data?.document_text ?? "";

  // The brief is a one-shot LLM pass over the tender document (POST /brief). Cached by react-query
  // so it isn't re-run every time the tab is opened; gated on a document actually being on file.
  const briefQ = useQuery({
    queryKey: ["pack-brief", packId],
    queryFn: () => tenderBrief(packId, docText),
    enabled: !!docText.trim(),
    staleTime: Infinity,
    retry: false,
  });

  if (packQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-white/[0.04]" />)}</div>;
  }

  if (!docText.trim()) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
        <span className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-white/[0.04] text-slate-500">
          <FileText className="size-6" />
        </span>
        <p className="text-sm font-semibold text-white">No tender document yet</p>
        <p className="mt-1 max-w-sm text-[12px] text-slate-500">Upload the RFP so the AI can produce a bid-context brief.</p>
        <button onClick={onOpenSources}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
          <Upload className="size-4" /> Go to Sources
        </button>
      </div>
    );
  }

  if (briefQ.isLoading) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
        <Loader2 className="mb-3 size-6 animate-spin text-indigo-400" />
        <p className="text-sm font-medium text-slate-200">Analysing the tender{"\u2026"}</p>
        <p className="mt-1 text-[12px] text-slate-500">Extracting scope, format, dates, success criteria and risks.</p>
      </div>
    );
  }

  if (briefQ.isError || !briefQ.data) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-red-500/20 bg-red-500/[0.06] px-4 py-12 text-center">
        <AlertTriangle className="mb-3 size-6 text-red-400" />
        <p className="text-sm font-medium text-red-200">Couldn&apos;t generate the brief</p>
        <button onClick={() => briefQ.refetch()}
          className="mt-4 rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-2 text-[13px] font-semibold text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
          Try again
        </button>
      </div>
    );
  }

  const b = briefQ.data;

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
          <ScrollText className="size-3.5" /> Summary
        </div>
        <div className="mt-2 text-[13px] leading-relaxed text-slate-300"><AnswerMarkdown text={b.summary || "\u2014"} /></div>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-violet-300">
          <Target className="size-3.5" /> Scope
        </div>
        <div className="mt-2 text-[13px] leading-relaxed text-slate-300"><AnswerMarkdown text={b.scope || "\u2014"} /></div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BriefList icon={<CalendarClock className="size-3.5" />} title="Key dates" tone="text-indigo-400" items={b.key_dates} />
        <BriefList icon={<Target className="size-3.5" />} title="Success criteria" tone="text-emerald-400" items={b.success_criteria} />
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <FileText className="size-3.5" /> Submission format
        </div>
        <div className="mt-2 text-[13px] leading-relaxed text-slate-300"><AnswerMarkdown text={b.submission_format || "\u2014"} /></div>
      </div>

      <BriefList icon={<ShieldAlert className="size-3.5" />} title="Gaps & risks" tone="text-amber-400" items={b.gaps_and_risks} warn />
    </div>
  );
}

function BriefList({ icon, title, tone, items, warn }: {
  icon: React.ReactNode; title: string; tone: string; items: string[]; warn?: boolean;
}) {
  return (
    <div className={`rounded-2xl border p-5 ${warn ? "border-amber-500/15 bg-amber-500/[0.03]" : "border-white/[0.06] bg-white/[0.015]"}`}>
      <div className={`flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider ${tone}`}>
        {icon} <span>{title}</span>
      </div>
      {items?.length ? (
        <ul className="mt-2.5 space-y-1.5">
          {items.map((it, i) => (
            <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-slate-300">
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
