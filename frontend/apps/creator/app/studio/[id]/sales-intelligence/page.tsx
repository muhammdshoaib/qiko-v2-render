"use client";

import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowRight, CalendarClock, ClipboardCheck, Radar, Wallet,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { listAgents, listSalesOpportunities, listSalesSources, type SalesIntelSource, type SalesOpportunity } from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import {
  deadlineLabel, deadlineUrgencyClass, formatCompact, formatDate, humanize,
  scoreBadgeClass, sourceLabel, stageBadgeClass, STAGE_LABELS,
} from "@/components/sales-intelligence/utils";

// Stage groupings for the five validated headline counts + pipeline-value bands. Every stage maps
// to exactly one group so the counts reconcile against the total pipeline.
const QUALIFIED_STAGES = ["qualifying", "qualified"] as const;
const VALIDATED_STAGES = ["validated", "ready_salesforce", "push_pending", "pushed"] as const;
const REJECTED_STAGES = ["rejected", "push_failed"] as const;

export default function SalesIntelligenceOverviewPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const oppsQ = useQuery({
    queryKey: ["sales-opportunities", agentId],
    queryFn: () => listSalesOpportunities(agentId),
    retry: false,
  });
  const opps: SalesOpportunity[] = oppsQ.data?.opportunities ?? [];

  const sourcesQ = useQuery({ queryKey: ["sales-sources", agentId], queryFn: () => listSalesSources(agentId), retry: false });
  const sources: SalesIntelSource[] = sourcesQ.data?.sources ?? [];

  const openDetail = (id: number) => router.push(`/studio/${agentId}/sales-intelligence/pipeline/${id}`);

  const metrics = useMemo(() => {
    const inGroup = (o: SalesOpportunity, g: readonly string[]) => g.includes(o.stage);
    const newFound = opps.filter((o) => o.stage === "ingested");
    const qualified = opps.filter((o) => inGroup(o, QUALIFIED_STAGES));
    const needsReview = opps.filter((o) => o.stage === "awaiting_review");
    const validated = opps.filter((o) => inGroup(o, VALIDATED_STAGES));
    const rejected = opps.filter((o) => inGroup(o, REJECTED_STAGES));
    const sumValue = (list: SalesOpportunity[]) => list.reduce((s, o) => s + (o.estimatedValue ?? 0), 0);
    const active = opps.filter((o) => !inGroup(o, REJECTED_STAGES));
    return {
      newFound: newFound.length,
      qualified: qualified.length,
      needsReview: needsReview.length,
      validated: validated.length,
      rejected: rejected.length,
      totalValue: sumValue(active),
      qualifiedValue: sumValue(qualified),
      validatedValue: sumValue(validated),
      needsReviewList: needsReview,
    };
  }, [opps]);

  // Nearest deadlines first (excludes rejected/failed); overdue items surface at the top in red.
  const upcoming = useMemo(() => {
    return opps
      .filter((o) => o.deadlineAt && !REJECTED_STAGES.includes(o.stage as (typeof REJECTED_STAGES)[number]))
      .sort((a, b) => (a.deadlineAt || "").localeCompare(b.deadlineAt || ""))
      .slice(0, 6);
  }, [opps]);

  const lastScan = useMemo(
    () => sources.map((s) => s.lastScanAt).filter(Boolean).sort().slice(-1)[0]
      ?? opps.map((o) => o.createdAt).filter(Boolean).sort().slice(-1)[0],
    [sources, opps],
  );
  const recent = useMemo(
    () => [...opps].sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || "")).slice(0, 5),
    [opps],
  );

  const loading = oppsQ.isLoading;
  const errored = oppsQ.isError;

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="overview">
      <div className="space-y-6">
        <OutcomesStrip title="OVERVIEW" tiles={[
          { value: String(metrics.newFound), label: "New Opportunities", caption: "awaiting qualification", trend: metrics.newFound > 0 ? "up" : "neutral" },
          { value: String(metrics.qualified), label: "Qualified", caption: "scored by AI", trend: "up" },
          { value: String(metrics.needsReview), label: "Needs Review", caption: "human validation queue", trend: metrics.needsReview > 0 ? "down" : "neutral" },
          { value: String(metrics.validated), label: "Validated", caption: "approved & pushed", trend: "up" },
          { value: String(metrics.rejected), label: "Rejected", caption: "no bid / declined", trend: metrics.rejected > 0 ? "down" : "neutral" },
        ]} />

        {errored && (
          <p className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
            <AlertTriangle className="size-4 shrink-0" /> Couldn&apos;t load opportunities. Try refreshing.
          </p>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Pipeline value: total + qualified + validated bands. */}
          <Card className="lg:col-span-1">
            <CardHeader icon={<Wallet className="size-3.5" />} title="Pipeline value" tint="text-emerald-400 bg-emerald-500/10" />
            {loading ? (
              <div className="mt-4 h-9 w-32 animate-pulse rounded bg-white/10" />
            ) : (
              <>
                <p className="mt-3 text-3xl font-bold tracking-tight text-white">{formatCompact(metrics.totalValue)}</p>
                <p className="text-[12px] text-slate-400">active opportunities</p>
                <dl className="mt-4 space-y-2 border-t border-white/[0.06] pt-4">
                  <div className="flex items-center justify-between text-[13px]">
                    <dt className="text-slate-400">Qualified</dt>
                    <dd className="font-semibold text-white">{formatCompact(metrics.qualifiedValue)}</dd>
                  </div>
                  <div className="flex items-center justify-between text-[13px]">
                    <dt className="text-slate-400">Validated</dt>
                    <dd className="font-semibold text-white">{formatCompact(metrics.validatedValue)}</dd>
                  </div>
                </dl>
              </>
            )}
          </Card>

          {/* Upcoming deadlines -- prominent, spanning two columns. */}
          <Card className="lg:col-span-2">
            <CardHeader icon={<CalendarClock className="size-3.5" />} title="Upcoming deadlines" tint="text-amber-400 bg-amber-500/10" />
            {loading ? (
              <div className="mt-4 space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-white/[0.04]" />)}</div>
            ) : upcoming.length === 0 ? (
              <EmptyRow icon={<CalendarClock className="size-5" />} text="No dated opportunities in the pipeline yet." />
            ) : (
              <ul className="mt-3 divide-y divide-white/[0.05]">
                {upcoming.map((o) => (
                  <li key={o.id}>
                    <button onClick={() => openDetail(o.id)}
                      className="flex w-full items-center gap-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 hover:bg-white/[0.02]">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-white">{o.title}</span>
                        <span className="block truncate text-[12px] text-slate-400">{o.buyer || sourceLabel(o.sourceKey)}</span>
                      </span>
                      <span className={cn("shrink-0 text-right text-[12px] font-semibold", deadlineUrgencyClass(o.deadlineAt))}>
                        <span className="block">{deadlineLabel(o.deadlineAt)}</span>
                        <span className="block text-[11px] font-normal text-slate-500">{formatDate(o.deadlineAt)}</span>
                      </span>
                      <ArrowRight className="size-4 shrink-0 text-slate-600" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Needs Review queue -- first-class review inbox. */}
          <Card>
            <div className="flex items-center justify-between">
              <CardHeader icon={<ClipboardCheck className="size-3.5" />} title="Needs review" tint="text-indigo-400 bg-indigo-500/10" />
              <span className="flex size-6 items-center justify-center rounded-full bg-white/[0.05] text-[11px] font-semibold text-slate-300">
                {metrics.needsReview}
              </span>
            </div>
            {loading ? (
              <div className="mt-4 space-y-2">{[0, 1].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-white/[0.04]" />)}</div>
            ) : metrics.needsReviewList.length === 0 ? (
              <EmptyRow icon={<ClipboardCheck className="size-5" />} text="Nothing waiting for human validation." />
            ) : (
              <ul className="mt-3 divide-y divide-white/[0.05]">
                {metrics.needsReviewList.slice(0, 6).map((o) => (
                  <li key={o.id}>
                    <button onClick={() => openDetail(o.id)}
                      className="flex w-full items-center gap-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 hover:bg-white/[0.02]">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-white">{o.title}</span>
                        <span className="block truncate text-[12px] text-slate-400">{o.buyer || sourceLabel(o.sourceKey)}</span>
                      </span>
                      {o.qualificationScore != null && (
                        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold", scoreBadgeClass(o.qualificationScore))}>
                          {o.qualificationScore}/100
                        </span>
                      )}
                      <ArrowRight className="size-4 shrink-0 text-slate-600" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Recent ingestion activity. */}
          <Card>
            <CardHeader icon={<Radar className="size-3.5" />} title="Recent ingestion" tint="text-violet-300 bg-violet-500/10" />
            <p className="mt-2 flex items-center gap-1.5 text-[12px] text-slate-400">
              <span className="size-1.5 rounded-full bg-emerald-400" />
              Last scan: {formatDate(lastScan, true)} &middot; {metrics.newFound} new to qualify
            </p>
            {loading ? (
              <div className="mt-4 space-y-2">{[0, 1].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-white/[0.04]" />)}</div>
            ) : recent.length === 0 ? (
              <EmptyRow icon={<Radar className="size-5" />} text="No opportunities ingested yet. Run a scan from Ingestion." />
            ) : (
              <ul className="mt-3 divide-y divide-white/[0.05]">
                {recent.map((o) => (
                  <li key={o.id}>
                    <button onClick={() => openDetail(o.id)}
                      className="flex w-full items-center gap-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 hover:bg-white/[0.02]">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-white">{o.title}</span>
                        <span className="block truncate text-[12px] text-slate-400">{o.buyer || sourceLabel(o.sourceKey)}</span>
                      </span>
                      <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", stageBadgeClass(o.stage))}>
                        {STAGE_LABELS[o.stage] ?? humanize(o.stage)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </CockpitShell>
  );
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5", className)}>{children}</div>;
}

function CardHeader({ icon, title, tint }: { icon: React.ReactNode; title: string; tint: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={cn("flex size-7 items-center justify-center rounded-lg", tint)}>{icon}</span>
      <h2 className="text-[14px] font-semibold text-white">{title}</h2>
    </div>
  );
}

function EmptyRow({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="mt-3 flex flex-col items-center px-4 py-8 text-center">
      <span className="mb-2 flex size-10 items-center justify-center rounded-2xl bg-white/[0.04] text-slate-500">{icon}</span>
      <p className="max-w-xs text-[12px] text-slate-400">{text}</p>
    </div>
  );
}
