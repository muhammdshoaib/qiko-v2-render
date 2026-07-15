"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowRight, Building2, CalendarClock, CheckCircle2, FileText, Sparkles,
} from "lucide-react";
import { getPackOverview, getRfpPack } from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";
import { OutcomesStrip, type OutcomeTile } from "@/components/cockpit/outcomes-strip";
import { truncate } from "@/components/pre-sales/utils";

export function OverviewTab({ packId, onOpenSections, onOpenBrief }: {
  packId: string; onOpenSections: () => void; onOpenBrief: () => void;
}) {
  const overviewQ = useQuery({ queryKey: ["pack-overview", packId], queryFn: () => getPackOverview(packId) });
  const packQ = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });

  const o = overviewQ.data;
  const pack = packQ.data;

  const tiles: OutcomeTile[] = [
    { value: o ? String(o.sections) : "\u2014", label: "Sections", caption: `${o?.sections_locked ?? 0} locked` },
    { value: o ? `${o.ai_drafted}/${o.ai_drafted_total}` : "\u2014", label: "AI-drafted", caption: "grounded in KB, cited", trend: "up" },
    { value: o ? String(o.for_human_review) : "\u2014", label: "For human review", caption: "before use", trend: o && o.for_human_review > 0 ? "down" : "neutral" },
    { value: o ? String(o.kb_sources) : "\u2014", label: "KB sources", caption: "real IDG documents", trend: "up" },
  ];

  return (
    <div className="space-y-6">
      <OutcomesStrip title="OVERVIEW" tiles={tiles} />

      {overviewQ.isError && (
        <p className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
          <AlertTriangle className="size-4 shrink-0" /> Couldn&apos;t load the tender overview. Try switching tenders or refreshing.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5 lg:col-span-2">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
              <FileText className="size-3.5" /> Tender summary
            </div>
            {pack && (
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-300">
                {pack.stage}
              </span>
            )}
          </div>

          {packQ.isLoading ? (
            <div className="mt-4 space-y-2">
              <div className="h-5 w-2/3 animate-pulse rounded bg-white/10" />
              <div className="h-3 w-1/3 animate-pulse rounded bg-white/10" />
            </div>
          ) : pack ? (
            <>
              <h2 className="mt-3 text-lg font-semibold text-white">{pack.title}</h2>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-slate-400">
                <span className="flex items-center gap-1.5">
                  <Building2 className="size-3.5 text-slate-500" /> {pack.client_name || "Buyer not set"}
                </span>
                <span className="flex items-center gap-1.5">
                  <CalendarClock className="size-3.5 text-slate-500" /> Due {formatShortDate(pack.deadline)}
                </span>
              </div>
              {pack.document_text?.trim() && (
                <p className="mt-3 text-[13px] leading-relaxed text-slate-400">{truncate(pack.document_text, 320)}</p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <button onClick={onOpenSections}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
                  Review answers <ArrowRight className="size-3.5" />
                </button>
                <button onClick={onOpenBrief}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-2 text-[13px] font-semibold text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
                  Tender brief
                </button>
              </div>
            </>
          ) : (
            <p className="mt-4 text-sm text-slate-500">Tender details unavailable.</p>
          )}
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-violet-300">
            <Sparkles className="size-3.5" /> How it works
          </div>
          <ol className="mt-3 space-y-3">
            {[
              "Upload the RFP -- it's parsed into sections and questions.",
              "AI drafts each answer grounded in your IDG knowledge base, with citations and a confidence score.",
              "Review, edit and lock each answer before it's used.",
              "Export a clean submission or an annotated review copy.",
            ].map((step, i) => (
              <li key={i} className="flex gap-2.5 text-[12px] leading-relaxed text-slate-400">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-indigo-500/15 text-[10px] font-bold text-indigo-300">{i + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          {o?.kb_gaps ? (
            <p className="mt-4 flex items-center gap-1.5 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] px-2.5 py-2 text-[11px] text-amber-300">
              <AlertTriangle className="size-3.5 shrink-0" /> {o.kb_gaps} question(s) flagged as KB gaps -- add sources to improve grounding.
            </p>
          ) : o ? (
            <p className="mt-4 flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] px-2.5 py-2 text-[11px] text-emerald-300">
              <CheckCircle2 className="size-3.5 shrink-0" /> No knowledge-base gaps detected.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
