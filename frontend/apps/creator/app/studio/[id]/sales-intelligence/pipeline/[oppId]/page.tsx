"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, Check, ExternalLink, HelpCircle, Loader2, Rocket, Sparkles, X,
} from "lucide-react";
import { cn } from "@qiko/ui";
import {
  getSalesOpportunity, listAgents, pushOpportunityToSalesforce, reviewSalesOpportunity,
  saveSalesOpportunityNotes, updateSalesOpportunity, type OpportunityDetail,
} from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { AssignReviewerControl } from "@/components/sales-intelligence/assign-reviewer-control";
import { DecisionHistoryView } from "@/components/sales-intelligence/decision-history-view";
import { Textarea } from "@/components/cockpit/controls";
import {
  formatDate, formatMoney, humanize, recommendationBadgeClass, scoreColor, sourceLabel,
  stageBadgeClass, STAGE_LABELS,
} from "@/components/sales-intelligence/utils";

const TABS = ["Overview", "Summary", "Qualification", "Reviewer", "Notes", "Status"] as const;

export default function OpportunityDetailPage() {
  const { id: agentId, oppId } = useParams<{ id: string; oppId: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const oppQ = useQuery({ queryKey: ["sales-opportunity", agentId, oppId], queryFn: () => getSalesOpportunity(agentId, oppId), retry: false });
  const opp = oppQ.data?.opportunity;
  const detail: OpportunityDetail | undefined = opp?.detail;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["sales-opportunity", agentId, oppId] });
    qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] });
  };
  const review = useMutation({
    mutationFn: (decision: "approve" | "reject") => reviewSalesOpportunity(agentId, oppId, decision),
    onSuccess: invalidate,
  });
  const push = useMutation({ mutationFn: () => pushOpportunityToSalesforce(agentId, oppId), onSuccess: invalidate });
  // No dedicated "run qualification" endpoint is documented yet on the Laravel controller list --
  // this bumps the stage as a stand-in until the real backend exposes a qualification-trigger
  // endpoint (the qualification scorer itself lives server-side, e.g. IdgSalesOpportunityService).
  const runQualification = useMutation({
    mutationFn: () => updateSalesOpportunity(agentId, oppId, { stage: "qualifying" }),
    onSuccess: invalidate,
  });

  if (oppQ.isLoading || !opp) {
    return (
      <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="pipeline">
        {oppQ.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Loader2 className="size-4 animate-spin" /> Loading opportunity{"\u2026"}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">This opportunity couldn&apos;t be found. It may have been archived or removed.</p>
            <button onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline`)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-semibold text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
              <ArrowLeft className="size-3.5" /> Back to pipeline
            </button>
          </div>
        )}
      </CockpitShell>
    );
  }

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="pipeline">
      <div className="space-y-5">
        <button onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline`)}
          className="flex items-center gap-1.5 rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
          <ArrowLeft className="size-4" /> Back to pipeline
        </button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex items-center gap-2">
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-300">
                {sourceLabel(opp.sourceKey)}
              </span>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${stageBadgeClass(opp.stage)}`}>
                {STAGE_LABELS[opp.stage] ?? humanize(opp.stage)}
              </span>
            </div>
            <h1 className="text-xl font-semibold leading-snug text-white">{opp.title}</h1>
            <p className="mt-1 text-[13px] text-slate-400">{[opp.buyer, opp.externalId].filter(Boolean).join(" \u00b7 ") || "-"}</p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {opp.sourceUrl && (
              <a href={opp.sourceUrl} target="_blank" rel="noreferrer"
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
                <ExternalLink className="size-3.5" /> Source
              </a>
            )}
            {(opp.stage === "ingested" || opp.stage === "qualifying") && (
              <button onClick={() => runQualification.mutate()} disabled={runQualification.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
                <Sparkles className={cn("size-3.5", runQualification.isPending && "animate-spin")} /> {runQualification.isPending ? "Running…" : "Run Qualification"}
              </button>
            )}
            {opp.stage === "awaiting_review" && (
              <>
                <button onClick={() => review.mutate("approve")} disabled={review.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-[13px] font-semibold text-white hover:bg-emerald-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 disabled:opacity-50">
                  <Check className="size-3.5" /> {review.isPending && review.variables === "approve" ? "Approving…" : "Approve"}
                </button>
                <button onClick={() => review.mutate("reject")} disabled={review.isPending}
                  className="flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[13px] font-semibold text-red-400 hover:bg-red-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60 disabled:opacity-50">
                  <X className="size-3.5" /> {review.isPending && review.variables === "reject" ? "Rejecting…" : "Reject"}
                </button>
              </>
            )}
            {(opp.stage === "validated" || opp.stage === "push_failed") && (
              <button onClick={() => push.mutate()} disabled={push.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
                <Rocket className="size-3.5" /> {push.isPending ? "Pushing…" : "Push to Salesforce"}
              </button>
            )}
          </div>
        </div>

        {(review.isError || push.isError || runQualification.isError) && (
          <p className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">
            <AlertTriangle className="size-3.5 shrink-0" />
            {push.isError ? "Couldn't push to Salesforce - try again in a moment."
              : review.isError ? "Couldn't save that review decision - try again."
              : "Couldn't run qualification - try again."}
          </p>
        )}

        <div role="tablist" aria-label="Opportunity detail sections" className="flex gap-1 overflow-x-auto border-b border-white/[0.06]">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)} role="tab" aria-selected={tab === t}
              className={cn("shrink-0 rounded-t-md px-3 py-2.5 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                tab === t ? "border-b-2 border-indigo-400 text-white" : "text-slate-400 hover:text-white")}>
              {t}
            </button>
          ))}
        </div>

        {tab === "Overview" && <OverviewTab opp={opp} detail={detail} />}
        {tab === "Summary" && <SummaryTab detail={detail} />}
        {tab === "Qualification" && <QualificationTab opp={opp} detail={detail} />}
        {tab === "Reviewer" && (
          <div className="space-y-4">
            <AssignReviewerControl agentId={agentId} opp={opp} onSaved={invalidate} />
            <DecisionHistoryView agentId={agentId} opportunityId={oppId} />
          </div>
        )}
        {tab === "Notes" && <NotesTab agentId={agentId} oppId={oppId} detail={detail} onSaved={invalidate} />}
        {tab === "Status" && <StatusTab opp={opp} detail={detail} />}
      </div>
    </CockpitShell>
  );
}

function Field({ label, value, tooltip }: { label: string; value: React.ReactNode; tooltip?: string }) {
  return (
    <div>
      <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
        {tooltip && <HelpCircle className="size-3" aria-label={tooltip} />}
      </p>
      <p className="mt-1.5 text-[14px] text-white">{value ?? "-"}</p>
    </div>
  );
}

function OverviewTab({ opp, detail }: { opp: import("@/lib/api").SalesOpportunity; detail?: OpportunityDetail }) {
  const ov = detail?.overview;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        <Field label="Deadline" value={formatDate(ov?.deadlineAt ?? opp.deadlineAt)} />
        <Field label="Estimated Value" value={formatMoney(ov?.estimatedValue ?? opp.estimatedValue, ov?.currency ?? opp.currency)} />
        <Field label="Country" value={ov?.country ?? opp.country} />
        <Field label="Category" value={ov?.category ?? opp.category} />
        <Field label="Reference" value={ov?.reference} />
        <Field label="Notice Type" value={ov?.noticeType} />
        <Field label="Security Clearance" value={ov?.securityClearance} />
        <Field label="Extraction Confidence" tooltip="Model confidence in the fields extracted from the source notice"
          value={ov?.extractionConfidence != null ? `${Math.round(ov.extractionConfidence)}%` : "-"} />
        <Field label="Framework" value={ov?.framework} />
        <Field label="Contract Duration" value={ov?.contractDuration} />
        <Field label="Technology" value={ov?.technology} />
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Contact</p>
        {ov?.contacts && ov.contacts.length > 0 ? (
          <div className="mt-2 space-y-1.5">
            {ov.contacts.map((c, i) => (
              <p key={i} className="text-[13px] text-slate-300">{[c.name, c.email, c.phone].filter(Boolean).join(" \u00b7 ") || "-"}</p>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-[13px] text-slate-500">{"-"}</p>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{title}</p>
      <div className="mt-2 text-[13px] leading-relaxed text-slate-300">{children}</div>
    </div>
  );
}

function SummaryTab({ detail }: { detail?: OpportunityDetail }) {
  const s = detail?.summary;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SummaryCard title="Executive Summary">{s?.executiveSummary ?? "-"}</SummaryCard>
        <SummaryCard title="Risk Summary">{s?.riskSummary ?? "-"}</SummaryCard>
        <SummaryCard title="Opportunity Summary">{s?.opportunitySummary ?? "-"}</SummaryCard>
        <SummaryCard title="Requirements">
          {s?.requirements && s.requirements.length > 0 ? (
            <ul className="list-disc space-y-1 pl-4">{s.requirements.map((r, i) => <li key={i}>{r}</li>)}</ul>
          ) : "-"}
        </SummaryCard>
      </div>
      <SummaryCard title="Deliverables">
        {s?.deliverables && s.deliverables.length > 0 ? (
          <ul className="list-disc space-y-1 pl-4">{s.deliverables.map((d, i) => <li key={i}>{d}</li>)}</ul>
        ) : "-"}
      </SummaryCard>
    </div>
  );
}

function ScoreGauge({ score }: { score: number | null | undefined }) {
  const pct = Math.max(0, Math.min(100, score ?? 0));
  const color = scoreColor(score);
  const circumference = 2 * Math.PI * 44;
  const dash = (pct / 100) * circumference;
  return (
    <svg width="112" height="112" viewBox="0 0 112 112" className="shrink-0">
      <circle cx="56" cy="56" r="44" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
      <circle cx="56" cy="56" r="44" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
        strokeDasharray={`${dash} ${circumference}`} transform="rotate(-90 56 56)" />
      <text x="56" y="52" textAnchor="middle" fontSize="26" fontWeight="700" fill="white">{score ?? "-"}</text>
      <text x="56" y="70" textAnchor="middle" fontSize="11" fill="#94a3b8">/ 100</text>
    </svg>
  );
}

function QualificationTab({ opp, detail }: { opp: import("@/lib/api").SalesOpportunity; detail?: OpportunityDetail }) {
  const q = detail?.qualification;
  const risks = q?.risks?.length ? q.risks : opp.risks ?? [];
  const missing = opp.missingFields ?? [];
  const blockers = q?.rejectionReasons ?? [];
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            AI Reasoning {q?.confidence != null && `\u00b7 ${Math.round(q.confidence)}% confidence`}
          </p>
          <div className="mt-3 flex items-start gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
              <Sparkles className="size-4" />
            </span>
            <p className="text-[13px] leading-relaxed text-slate-300">{q?.aiReasoning ?? "No AI reasoning captured yet."}</p>
          </div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Recommendations</p>
          {q?.recommendations && q.recommendations.length > 0 ? (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-[13px] text-slate-300">
              {q.recommendations.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          ) : <p className="mt-2 text-[13px] text-slate-500">No recommendations yet.</p>}
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-400">
            <AlertTriangle className="size-3.5" /> Risks &amp; missing info
          </p>
          {risks.length === 0 && missing.length === 0 && blockers.length === 0 ? (
            <p className="mt-2 text-[13px] text-slate-500">No risks or gaps flagged.</p>
          ) : (
            <div className="mt-3 space-y-3 text-[13px] text-slate-300">
              {risks.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Risks</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4">{risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              )}
              {blockers.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">No-bid reasons</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-red-300">{blockers.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              )}
              {missing.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Missing information</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {missing.map((m, i) => (
                      <span key={i} className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-400">
                        {humanize(m)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
          <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Overall Score <HelpCircle className="size-3" />
          </p>
          <div className="mt-3 flex items-center gap-4">
            <ScoreGauge score={q?.overallScore} />
            <div>
              <p className="text-[13px] text-slate-400">Qualification Score</p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-slate-300">
                {q?.overallScore != null
                  ? q.overallScore >= 70 ? "Strong fit - recommended to bid."
                    : q.overallScore >= 40 ? "Moderate fit - review flagged dimensions before approval."
                    : "Weak fit - likely no-bid."
                  : "Not yet scored."}
              </p>
              {q?.recommendation && (
                <span className={`mt-2 inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${recommendationBadgeClass(q.recommendation)}`}>
                  {q.recommendation}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
          <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Qualification by criteria <HelpCircle className="size-3" aria-label="Service fit, geography, value and clearance dimensions scored by the AI" />
          </p>
          {q?.dimensions && Object.keys(q.dimensions).length > 0 ? (
            <div className="mt-3 space-y-3">
              {Object.entries(q.dimensions).map(([dim, val]) => (
                <div key={dim}>
                  <div className="flex items-center justify-between text-[13px]">
                    <span className="text-slate-400">{humanize(dim)}</span>
                    <span className="font-semibold text-white">{val}</span>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
                    <div className="h-full rounded-full bg-indigo-400" style={{ width: `${Math.max(0, Math.min(100, Number(val) || 0))}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="mt-2 text-[13px] text-slate-500">No criteria scores available yet.</p>}
        </div>
      </div>
    </div>
  );
}

function NotesTab({ agentId, oppId, detail, onSaved }: { agentId: string; oppId: string; detail?: OpportunityDetail; onSaved: () => void }) {
  const [notes, setNotes] = useState(detail?.notes.humanReviewNotes ?? "");
  const save = useMutation({ mutationFn: () => saveSalesOpportunityNotes(agentId, oppId, notes), onSuccess: onSaved });

  const dirty = notes !== (detail?.notes.humanReviewNotes ?? "");
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <label htmlFor="human-review-notes" className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Human Review Notes</label>
      <Textarea id="human-review-notes" value={notes} onChange={(e) => setNotes(e.target.value)}
        placeholder="Add context for reviewers -- e.g. why this was approved, rejected, or needs follow-up."
        className="mt-3 min-h-32" />
      <div className="mt-3 flex items-center justify-end gap-3">
        {save.isSuccess && !dirty && <span className="text-[12px] text-emerald-400">Saved</span>}
        <button onClick={() => save.mutate()} disabled={save.isPending || !dirty}
          className="rounded-lg bg-indigo-500 px-4 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
          {save.isPending ? "Saving…" : "Save Notes"}
        </button>
      </div>
      {detail?.notes.updatedAt && <p className="mt-2 text-[11px] text-slate-500">Last updated {formatDate(detail.notes.updatedAt, true)}</p>}
    </div>
  );
}

function Pill({ value }: { value: string | null | undefined }) {
  return (
    <span className="inline-flex rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[12px] font-medium text-slate-200">
      {value ?? "-"}
    </span>
  );
}

function StatusTab({ opp, detail }: { opp: import("@/lib/api").SalesOpportunity; detail?: OpportunityDetail }) {
  const c = detail?.completed;
  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Status</p>
        <div className="mt-1.5"><Pill value={c?.isComplete ? "Completed" : "In progress"} /></div>
      </div>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Stage</p>
        <div className="mt-1.5"><Pill value={STAGE_LABELS[opp.stage] ?? opp.stage} /></div>
      </div>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Review Status</p>
        <div className="mt-1.5"><Pill value={humanize(c?.humanReviewStatus ?? opp.humanReviewStatus ?? "Needs Review")} /></div>
      </div>
      <Field label="Reviewed By" value={c?.reviewedBy?.userName ?? opp.reviewedBy?.userName} />
      <Field label="Reviewed At" value={formatDate(c?.reviewedAt ?? opp.reviewedAt)} />
      <Field label="Completed At" value={formatDate(c?.completedAt)} />
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Salesforce Push Status</p>
        <div className="mt-1.5"><Pill value={humanize(c?.salesforcePushStatus ?? opp.salesforcePushStatus ?? "Not Started")} /></div>
      </div>
      <Field label="Salesforce Opportunity ID" value={c?.salesforceOpportunityId ?? opp.salesforceOpportunityId} />
      <Field label="Salesforce Pushed At" value={formatDate(c?.salesforcePushedAt ?? opp.salesforcePushedAt)} />
    </div>
  );
}
