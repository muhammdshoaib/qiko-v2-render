"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowRight, BookMarked, Building2, CalendarClock, CheckCircle2, FileText, Files,
  Sparkles,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { getBrief, getPackOverview, getRfpPack, getTenderStatus } from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";
import { OutcomesStrip, type OutcomeTile } from "@/components/cockpit/outcomes-strip";
import { truncate } from "@/components/pre-sales/utils";

// A parsed document's character count is a good enough proxy for its size, shown human-readably so
// reviewers can sanity-check that the right (non-empty) files went into the tender.
function formatCharSize(chars: number): string {
  if (!chars || chars < 0) return "0 chars";
  if (chars < 1000) return `${chars} chars`;
  if (chars < 1_000_000) return `${(chars / 1000).toFixed(1)}k chars`;
  return `${(chars / 1_000_000).toFixed(1)}M chars`;
}

export function OverviewTab({ packId, onOpenSections, onOpenBrief }: {
  packId: string; onOpenSections: () => void; onOpenBrief: () => void;
}) {
  const overviewQ = useQuery({ queryKey: ["pack-overview", packId], queryFn: () => getPackOverview(packId) });
  const packQ = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });
  const statusQ = useQuery({ queryKey: ["tender-status", packId], queryFn: () => getTenderStatus(packId) });
  const briefQ = useQuery({ queryKey: ["pack-brief", packId], queryFn: () => getBrief(packId) });

  const o = overviewQ.data;
  const pack = packQ.data;

  // Prefer the clean AI brief summary. Fall back to the raw tender text with the multi-document
  // "===== DOCUMENT: name =====" headers stripped, so the summary card never shows those markers.
  const summaryText = briefQ.data?.summary?.trim()
    || (pack?.document_text ? pack.document_text.replace(/=====\s*DOCUMENT:.*?=====/g, " ").replace(/\s+/g, " ").trim() : "");

  // KB gaps are only KNOWN once answers are drafted (a gap = a question that couldn't be grounded in
  // the KB), so hold the neutral message until drafting is done to avoid a "no gaps" claim flipping to
  // "has gaps" as answers land.
  // Drafting is "complete" when the background job reports it (ready, or partial = finished with some
  // failures). Do NOT require ai_drafted >= ai_drafted_total: manual/commercial sections are never
  // AI-drafted, so that ratio never reaches 100% and the neutral message would show forever even
  // after every answer that CAN be drafted has been. Fall back to "has drafts" for legacy packs
  // that predate gen_status.
  const draftsState = statusQ.data?.drafts?.state;
  const draftingComplete = draftsState === "ready" || draftsState === "partial"
    || (!draftsState && !!o && o.ai_drafted > 0);

  const tiles: OutcomeTile[] = [
    { value: o ? String(o.sections) : "-", label: "Sections", caption: `${o?.sections_locked ?? 0} locked` },
    { value: o ? `${o.ai_drafted}/${o.ai_drafted_total}` : "-", label: "AI-drafted", caption: "grounded in KB, cited", trend: "up" },
    { value: o ? String(o.for_human_review) : "-", label: "For human review", caption: "before use", trend: o && o.for_human_review > 0 ? "down" : "neutral" },
    { value: o ? String(o.kb_sources) : "-", label: "KB sources", caption: "real IDG documents", trend: "up" },
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
              {summaryText && (
                <p className="mt-3 text-[13px] leading-relaxed text-slate-400">{truncate(summaryText, 320)}</p>
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
          {!o ? null : !draftingComplete ? (
            // Drafting still in progress: never claim "no gaps" (it can flip to "has gaps" as more
            // answers land). Hold the neutral message until every answer is generated.
            <p className="mt-4 flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-2 text-[11px] text-slate-400">
              <AlertTriangle className="size-3.5 shrink-0" /> Knowledge-base gaps are flagged once answers are generated.
            </p>
          ) : o.kb_gaps > 0 ? (
            <p className="mt-4 flex items-center gap-1.5 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] px-2.5 py-2 text-[11px] text-amber-300">
              <AlertTriangle className="size-3.5 shrink-0" /> {o.kb_gaps} question(s) flagged as KB gaps -- add sources to improve grounding.
            </p>
          ) : (
            <p className="mt-4 flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] px-2.5 py-2 text-[11px] text-emerald-300">
              <CheckCircle2 className="size-3.5 shrink-0" /> No knowledge-base gaps detected.
            </p>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
          <Files className="size-3.5" /> Source documents
        </div>
        <p className="mt-1 text-[12px] text-slate-500">Documents used to parse and answer this tender.</p>

        {/* Knowledge Base Reference (IDG-1000). Absence is rendered explicitly rather than left
            blank: a reviewer has to be able to tell at a glance whether a draft was allowed to
            draw on the whole knowledge base or only one document. */}
        {!packQ.isLoading && (
          <div className={cn(
            "mt-4 flex items-start gap-2 rounded-lg border px-3 py-2.5 text-[12px]",
            pack?.reference_doc_id
              ? "border-indigo-500/20 bg-indigo-500/[0.06] text-indigo-200"
              : "border-white/[0.06] bg-white/[0.02] text-slate-400",
          )}>
            <BookMarked className="mt-0.5 size-3.5 shrink-0" />
            {pack?.reference_doc_id ? (
              <span className="min-w-0">
                Answers restricted to <span className="font-semibold">{pack.reference_doc_id}</span>.
                No other knowledge base document was used.
              </span>
            ) : (
              <span className="min-w-0">Answers drew on the full knowledge base.</span>
            )}
          </div>
        )}

        {packQ.isLoading ? (
          <div className="mt-4 space-y-2">
            <div className="h-9 w-full animate-pulse rounded-lg bg-white/[0.04]" />
            <div className="h-9 w-2/3 animate-pulse rounded-lg bg-white/[0.04]" />
          </div>
        ) : pack?.source_documents && pack.source_documents.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {pack.source_documents.map((doc, i) => (
              <li key={`${doc.name}-${i}`}
                className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
                <FileText className="size-4 shrink-0 text-slate-500" />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-slate-200">{doc.name}</span>
                <span className="shrink-0 text-[11px] text-slate-500">{formatCharSize(doc.chars)}</span>
                <span className="shrink-0 text-[11px] text-slate-500">{formatShortDate(doc.uploaded_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-3 text-[12px] text-slate-400">
            <AlertTriangle className="size-3.5 shrink-0" /> No source documents recorded for this tender yet.
          </p>
        )}
      </div>
    </div>
  );
}
