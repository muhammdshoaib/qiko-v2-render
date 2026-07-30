"use client";

// Worker landing page for the Pre-Sales / RFP Writer worker. Shown when the cockpit is opened
// without a ?pack= deep-link. A left "USE CASES" rail switches between three live views
// (AI Response Generation, Knowledge Base, Section Assignment) with three further locked use-cases
// teased below. Matches the cockpit-shell dark theme (bg-[#05070d], indigo/violet accents).
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, BarChart3, Building2, Check, FileText, LayoutList, Lock, Monitor, Pencil, Plus, ShieldCheck,
  Users, X,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { getPackOverview, listDocuments, type PackOverview, type RfpPack } from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";
import { OutcomesStrip, type OutcomeTile } from "@/components/cockpit/outcomes-strip";
import { SourcesTab } from "@/components/pre-sales/sources-tab";
import { SectionAssignment } from "@/components/pre-sales/section-assignment";
import { NewTenderPanel } from "@/components/pre-sales/new-tender-panel";
import {
  AI_DRAFTING_DESCRIPTION,
  activeBidPacks,
  aiDraftingPercent,
  knowledgeChunkCount,
  nextBidDeadline,
} from "@/components/pre-sales/metrics";
import { MetricInfoTooltip } from "@/components/pre-sales/metric-info-tooltip";
import { OutcomeDialog } from "@/components/pre-sales/outcome-dialog";

type LandingView = "ai_response" | "knowledge" | "section_assignment";

// Live tender status from the generation pipeline (mirrors app/workers/[id]/page.tsx and the
// tenders-list, kept in step so the pill reads the same across views).
function tenderStatusLabel(p: RfpPack): string {
  const g = p.gen_status;
  const drafts = g?.drafts?.state;
  if (drafts === "ready") return "Ready for review";
  if (drafts === "partial") return "Drafting (partial)";
  if (drafts === "running" || drafts === "pending") return "Drafting";
  if (g?.sections === "error" || g?.requirements === "error") return "Parse error";
  if (g?.sections === "running" || g?.sections === "pending" || g?.requirements === "running" || g?.requirements === "pending") return "Parsing";
  return p.stage || "parsed";
}

function tenderStatusClass(p: RfpPack): string {
  const drafts = p.gen_status?.drafts?.state;
  if (drafts === "ready") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (drafts === "partial") return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  if (drafts === "running" || drafts === "pending") return "border-indigo-500/30 bg-indigo-500/10 text-indigo-300";
  if (p.gen_status?.sections === "error" || p.gen_status?.requirements === "error") return "border-red-500/30 bg-red-500/10 text-red-400";
  return "border-white/10 bg-white/[0.04] text-slate-400";
}

function OutcomePill({ outcome }: { outcome: RfpPack["outcome"] }) {
  const label = outcome ?? "pending";
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold capitalize",
      outcome === "won" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
        : outcome === "lost" ? "border-red-500/30 bg-red-500/10 text-red-400"
          : outcome === "withdrawn" ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
            : "border-white/10 bg-white/[0.04] text-slate-400")}>
      {outcome === "won" ? <Check className="size-3" /> : outcome === "lost" ? <X className="size-3" /> : null}
      {label}
    </span>
  );
}

const USE_CASES: { view: LandingView; label: string; sub: string; icon: typeof FileText }[] = [
  { view: "ai_response", label: "AI Response Generation", sub: "DOCUMENT", icon: FileText },
  { view: "knowledge", label: "Knowledge Base", sub: "MONITOR", icon: Monitor },
  { view: "section_assignment", label: "Section Assignment", sub: "LIST", icon: LayoutList },
];

const LOCKED_USE_CASES: { label: string; icon: typeof ShieldCheck }[] = [
  { label: "Compliance Checker", icon: ShieldCheck },
  { label: "Win/Loss Analysis", icon: BarChart3 },
  { label: "Teams Integration", icon: Users },
];

export function WorkerLanding({ agentId, workerName, packs, onOpenPack }: {
  agentId: string; workerName: string; packs: RfpPack[]; onOpenPack: (packId: string) => void;
}) {
  const router = useRouter();
  const [view, setView] = useState<LandingView>("ai_response");
  const [showNew, setShowNew] = useState(false);
  const [outcomePack, setOutcomePack] = useState<RfpPack | null>(null);
  const [outcomeTrigger, setOutcomeTrigger] = useState<HTMLButtonElement | null>(null);
  const activePacks = useMemo(() => activeBidPacks(packs), [packs]);

  // Per-pack overview drives the AI-drafted / For human review tiles. Fetched per pack so the
  // aggregate is honest (real drafting counts, not estimates); tiles that need it fall back to "-"
  // until the overviews resolve.
  const overviewQs = useQueries({
    queries: activePacks.map((p) => ({
      queryKey: ["pack-overview", p.id],
      queryFn: () => getPackOverview(p.id),
    })),
  });
  const overviews = useMemo(
    () => overviewQs.map((q) => q.data).filter((d): d is PackOverview => !!d),
    [overviewQs],
  );

  const docsQ = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const dataVolume = knowledgeChunkCount(docsQ.data ?? []);
  const aiDrafting = aiDraftingPercent(activePacks);

  const finalised = packs.filter((p) => p.stage === "final" || !!p.outcome).length;
  const aiDrafted = overviews.reduce((n, o) => n + o.ai_drafted, 0);
  const aiDraftedTotal = overviews.reduce((n, o) => n + o.ai_drafted_total, 0);
  const forHumanReview = overviews.reduce((n, o) => n + o.for_human_review, 0);
  const haveOverviews = overviews.length > 0;

  const tiles: OutcomeTile[] = [
    { value: haveOverviews ? `${aiDrafted}/${aiDraftedTotal}` : "-", label: "AI-drafted", caption: "grounded in KB, cited", trend: "up" },
    { value: haveOverviews ? String(forHumanReview) : "-", label: "For human review", caption: "before use", trend: forHumanReview > 0 ? "down" : "neutral" },
    { value: String(finalised), label: "RFPs finalised", caption: "closed or delivered" },
    { value: String(activePacks.length), label: "Active bids", caption: "in progress" },
  ];

  const stats: { label: string; value: string; description?: string }[] = [
    { label: "Active Bids", value: String(activePacks.length) },
    {
      label: "AI Drafting",
      value: aiDrafting === null ? "-" : `${aiDrafting}%`,
      description: AI_DRAFTING_DESCRIPTION,
    },
    { label: "Data Volume", value: `${dataVolume} chunks` },
    { label: "Next Bid", value: formatShortDate(nextBidDeadline(activePacks, Date.now())) },
  ];

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-[#05070d] text-slate-200">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-white/[0.06] px-3 sm:px-4">
        <button onClick={() => router.push("/studio")} className="flex shrink-0 items-center gap-1.5 rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
          <ArrowLeft className="size-4" /> <span className="hidden sm:inline">Studio</span>
        </button>
        <span className="hidden h-4 w-px bg-white/10 sm:block" />
        <span className="hidden size-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/15 text-indigo-400 sm:flex">
          <FileText className="size-3.5" />
        </span>
        <div className="flex min-w-0 flex-col">
          <h1 className="truncate text-sm font-semibold leading-tight text-white">{workerName}</h1>
          <p className="flex items-center gap-1 text-[10px] leading-tight text-slate-500">
            <span className="size-1.5 rounded-full bg-emerald-400" /> IDG Security &middot; Ready
          </p>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* USE CASES rail */}
        <nav aria-label="Use cases" className="hidden w-[230px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-white/[0.06] px-4 py-5 lg:flex">
          <div>
            <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Use cases</p>
            <div className="flex flex-col gap-1">
              {USE_CASES.map((item) => {
                const isActive = item.view === view;
                const Icon = item.icon;
                return (
                  <button
                    key={item.view}
                    onClick={() => setView(item.view)}
                    aria-current={isActive ? "page" : undefined}
                    className={cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                      isActive ? "border border-indigo-500/30 bg-indigo-500/10 text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white")}
                  >
                    <Icon className={cn("size-4 shrink-0", isActive ? "text-indigo-400" : "text-slate-500")} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{item.label}</span>
                      <span className="block text-[10px] uppercase tracking-wider text-slate-500">{item.sub}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="mt-1 flex flex-col gap-1">
              {LOCKED_USE_CASES.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.label}
                    type="button"
                    disabled
                    aria-disabled="true"
                    title="Locked"
                    className="flex cursor-not-allowed items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-slate-600 opacity-70"
                  >
                    <Icon className="size-4 shrink-0 text-slate-600" />
                    <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{item.label}</span>
                    <Lock className="size-3.5 shrink-0 text-slate-600" />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Bottom stats block */}
          <div className="mt-auto grid grid-cols-2 gap-2">
            {stats.map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5"
              >
                <p className="flex items-center gap-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-500">
                  <span>{s.label}</span>
                  {s.description && (
                    <MetricInfoTooltip label={s.label} description={s.description} />
                  )}
                </p>
                <p className="mt-1 truncate text-[15px] font-bold text-white">{s.value}</p>
              </div>
            ))}
          </div>
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Mobile use-case switcher */}
          <nav aria-label="Use cases" className="flex shrink-0 gap-1.5 overflow-x-auto border-b border-white/[0.06] px-3 py-2 lg:hidden">
            {USE_CASES.map((item) => {
              const isActive = item.view === view;
              const Icon = item.icon;
              return (
                <button
                  key={item.view}
                  onClick={() => setView(item.view)}
                  aria-current={isActive ? "page" : undefined}
                  className={cn("flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                    isActive ? "border border-indigo-500/30 bg-indigo-500/10 text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white")}
                >
                  <Icon className={cn("size-3.5 shrink-0", isActive ? "text-indigo-400" : "text-slate-500")} />
                  <span className="whitespace-nowrap">{item.label}</span>
                </button>
              );
            })}
          </nav>

          <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4 lg:px-6 lg:py-6">
            {view === "ai_response" ? (
              <div className="space-y-6">
                <OutcomesStrip title="AI RESPONSE GENERATION" tiles={tiles} />

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-white">AI Response Generation</h2>
                    <p className="mt-0.5 text-[13px] text-slate-500">Your RFPs and proposals</p>
                  </div>
                  <button
                    onClick={() => setShowNew(true)}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                  >
                    <Plus className="size-4" /> New RFP
                  </button>
                </div>

                {packs.length === 0 ? (
                  <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
                    <FileText className="mb-3 size-9 text-slate-600" />
                    <p className="text-sm font-semibold text-white">No RFPs yet</p>
                    <p className="mt-1 max-w-xs text-[13px] text-slate-500">Upload your first RFP to start drafting a grounded response.</p>
                  </div>
                ) : (
                  <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                    {packs.map((p) => {
                      const docs = p.source_documents ?? [];
                      return (
                        <li key={p.id}>
                          <article className="flex h-full flex-col rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4 transition-colors hover:bg-white/[0.03]">
                            <button
                              type="button"
                              onClick={() => onOpenPack(p.id)}
                              className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <p className="min-w-0 flex-1 truncate text-[14px] font-semibold text-white">{p.title}</p>
                                <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium", tenderStatusClass(p))}>
                                  {tenderStatusLabel(p)}
                                </span>
                              </div>
                              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-slate-400">
                                <span className="flex items-center gap-1.5">
                                  <FileText className="size-3.5 text-slate-500" /> {docs.length} document{docs.length === 1 ? "" : "s"}
                                </span>
                                <span className="flex items-center gap-1.5">
                                  <Building2 className="size-3.5 text-slate-500" /> {p.client_name || "No client set"}
                                </span>
                                <span>Due {formatShortDate(p.deadline)}</span>
                                <OutcomePill outcome={p.outcome} />
                              </div>
                              {docs.length > 0 && (
                                <div className="mt-3 flex flex-wrap gap-1.5">
                                  {docs.map((d, i) => (
                                    <span key={`${d.name}-${i}`} className="max-w-[180px] truncate rounded-md border border-white/[0.06] bg-white/[0.03] px-2 py-0.5 text-[11px] text-slate-400">
                                      {d.name}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </button>
                            <div className="mt-auto flex justify-end border-t border-white/[0.06] pt-3">
                              <button
                                type="button"
                                onClick={(event) => {
                                  setOutcomeTrigger(event.currentTarget);
                                  setOutcomePack(p);
                                }}
                                aria-label={`Edit outcome for ${p.title}`}
                                className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold text-cyan-300 hover:bg-cyan-400/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                              >
                                <Pencil className="size-3.5" aria-hidden="true" /> Edit outcome
                              </button>
                            </div>
                          </article>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            ) : view === "knowledge" ? (
              <SourcesTab />
            ) : (
              <SectionAssignment packs={packs} agentId={agentId} />
            )}
          </main>
        </div>
      </div>

      {outcomePack && (
        <OutcomeDialog
          pack={outcomePack}
          agentId={agentId}
          open
          onOpenChange={(open) => {
            if (open) return;
            const trigger = outcomeTrigger;
            setOutcomePack(null);
            requestAnimationFrame(() => {
              trigger?.focus();
              setOutcomeTrigger(null);
            });
          }}
        />
      )}

      {showNew && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 px-4 py-10 backdrop-blur-sm">
          <NewTenderPanel
            agentId={agentId}
            onCreated={(packId) => { setShowNew(false); onOpenPack(packId); }}
            onCancel={() => setShowNew(false)}
          />
        </div>
      )}
    </div>
  );
}
