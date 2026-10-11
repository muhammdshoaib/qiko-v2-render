"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Building2, Radar, Sparkles } from "lucide-react";
import { Button, cn } from "@qiko/ui";
import { toast } from "sonner";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { studioAttention, useBrain } from "@/lib/brain/store";
import {
  COMPANY_SUMMARY,
  RECENT_ACTIONS,
  type ShowcaseOutcome,
  type ShowcaseWorker,
} from "@/lib/studio/showcase";

const CARD = "rounded-2xl border border-white/[0.06] bg-white/[0.015]";
const ICONS = {
  "property-insights": Building2,
  "intent-intelligence": Radar,
} as const;

export function StudioHome({ workers }: { workers: ShowcaseWorker[] }) {
  const router = useRouter();
  const brain = useBrain();
  const attention = !brain.ready ? [] : studioAttention(brain.approval).filter((item) => item.status === "attention");
  const completedReview = !brain.ready ? [] : studioAttention(brain.approval).filter((item) => item.status === "completed");
  const summaryPoints = COMPANY_SUMMARY.points.map((point) =>
    point.label === "Awaiting review"
      ? { ...point, value: !brain.ready ? "—" : brain.approval === "awaiting" ? "1" : "0" }
      : point,
  );

  return (
    <div className="mx-auto w-full max-w-6xl space-y-8 px-4 py-6 sm:px-6 sm:py-10 lg:px-12">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>
            Studio
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            Deployed workers and the outcomes they are delivering.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/studio/intelligence"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-[13px] text-slate-400 underline-offset-4 hover:text-white hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
          >
            How they connect
          </Link>
          <Button type="button" onClick={() => router.push("/workers")}>
            Deploy worker
          </Button>
        </div>
      </header>

      <section className={cn(CARD, "p-5")} aria-labelledby="company-intel-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Company intelligence</p>
            <h2 id="company-intel-heading" className="mt-1 text-base font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
              {COMPANY_SUMMARY.headline}
            </h2>
          </div>
          <HonestyBadge kind="illustrative" />
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {summaryPoints.map((point) => (
            <div key={point.label} className="rounded-xl border border-white/[0.04] bg-white/[0.02] px-3 py-3">
              <dt className="text-[11px] text-slate-500">{point.label}</dt>
              <dd className="mt-1 text-lg font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{point.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <OutcomeList
          title="Needs attention"
          empty="Nothing waiting on you."
          items={attention}
          onApprove={brain.approval === "awaiting" ? () => toast.message(brain.approveFollowUp()) : undefined}
          onHold={brain.approval === "awaiting" ? () => toast.message(brain.holdFollowUp()) : undefined}
        />
        <OutcomeList
          title="Recent worker actions"
          empty="No recent actions."
          items={[...completedReview, ...RECENT_ACTIONS]}
        />
      </div>

      <section aria-labelledby="workers-heading">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 id="workers-heading" className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
            Deployed workers
          </h2>
          <p className="text-[12px] text-slate-500">Inspect a worker, then explore how they connect.</p>
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          {workers.map((worker) => {
            const Icon = ICONS[worker.slug];
            return (
              <article
                key={worker.slug}
                className="overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.015]"
              >
                <div className="px-6 pt-6 pb-4">
                  <div className="mb-5 flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3.5">
                      <span className="flex size-11 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                        <Icon className="size-5" />
                      </span>
                      <div>
                        <h3 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{worker.name}</h3>
                        <p className="mt-0.5 text-[12px] text-slate-500">{worker.role}</p>
                      </div>
                    </div>
                    <span className="flex items-center gap-1.5 rounded-full bg-emerald-400/[0.08] px-2.5 py-[3px] text-[9px] font-semibold uppercase tracking-wider text-emerald-400/80">
                      <span className="size-1.5 rounded-full bg-emerald-400" /> Active
                    </span>
                  </div>
                  <p className="text-[13px] leading-relaxed text-slate-400">{worker.purpose}</p>
                  <p className="mt-3 text-[12px] text-slate-500">{worker.activity}</p>
                  {worker.insights[0] && (
                    <p className="mt-3 rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2.5 text-[12px] leading-relaxed text-slate-300">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Recent outcome</span>
                      <span className="mt-1 block text-white">{worker.insights[0].title}</span>
                      {worker.insights[0].detail}
                    </p>
                  )}
                  <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {worker.metrics.map((metric) => (
                      <div key={metric.label} className="rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2.5">
                        <dd className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{metric.value}</dd>
                        <dt className="mt-0.5 text-[10px] text-slate-500">{metric.label}</dt>
                      </div>
                    ))}
                  </dl>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.05] px-6 py-3">
                  <Link
                    href={`/studio/w/${worker.slug}`}
                    className="inline-flex min-h-11 items-center gap-1 text-[13px] text-white hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                  >
                    Inspect worker <ArrowRight className="size-3.5" />
                  </Link>
                  <Link
                    href={`/studio/intelligence?focus=${worker.slug}`}
                    className="inline-flex min-h-11 items-center gap-1 text-[13px] text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                  >
                    <Sparkles className="size-3.5" /> In intelligence
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function OutcomeList({
  title,
  empty,
  items,
  onApprove,
  onHold,
}: {
  title: string;
  empty: string;
  items: ShowcaseOutcome[];
  onApprove?: () => void;
  onHold?: () => void;
}) {
  return (
    <section className={cn(CARD, "p-5")} aria-label={title}>
      <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{title}</h2>
      {items.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {items.map((item) => (
            <li key={item.title} className="rounded-xl border border-white/[0.04] bg-white/[0.02]">
              {item.href ? (
                <Link
                  href={item.href}
                  className="block px-3 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                >
                  <OutcomeBody item={item} />
                </Link>
              ) : (
                <div className="px-3 py-3">
                  <OutcomeBody item={item} />
                </div>
              )}
              {item.status === "attention" && onApprove && onHold && (
                <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.04] px-3 py-2">
                  <Button type="button" size="sm" onClick={onApprove}>Approve review</Button>
                  <Button type="button" size="sm" variant="outline" onClick={onHold}>Hold</Button>
                  <Link
                    href="/studio/intelligence?tab=channels&surface=claude"
                    className="inline-flex min-h-11 items-center text-[12px] text-slate-400 underline-offset-4 hover:text-white hover:underline"
                  >
                    Review in Claude
                  </Link>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OutcomeBody({ item }: { item: ShowcaseOutcome }) {
  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-white">{item.title}</p>
        <span className={cn("shrink-0 text-[10px] uppercase tracking-wider", item.status === "attention" ? "text-amber-300" : "text-slate-500")}>
          {item.status === "attention" ? "Review" : "Done"}
        </span>
      </div>
      <p className="mt-1 text-[12px] text-slate-400">{item.detail}</p>
      <p className="mt-2 text-[11px] text-slate-500">{item.at}</p>
    </>
  );
}
