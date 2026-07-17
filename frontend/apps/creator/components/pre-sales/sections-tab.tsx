"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ChevronDown, ChevronRight, Lock, Unlock, Loader2, RefreshCw, Copy, Save,
  ArrowLeft, ArrowRight, FileSpreadsheet, ListChecks, CheckCircle2, Upload, Users, X, Check,
} from "lucide-react";
import { cn } from "@qiko/ui";
import {
  listPackSections, generatePackQuestion, savePackQuestionDraft,
  lockPackQuestion, unlockPackQuestion, lockAllInPackSection,
  getTenderStatus, getAssignees, setSectionReviewer, confirmAssignments,
  type PackSectionNode, type PackQuestion, type TenderGenStatus, type GenState, type Assignee,
} from "@/lib/api";
import { AnswerMarkdown } from "@/components/chat-message";
import { OutcomesStrip } from "@/components/cockpit/outcomes-strip";
import { Textarea } from "@/components/cockpit/controls";
import {
  confidenceBadgeClass, confidenceClass, confidencePct, sectionStatusBadgeClass, sectionStatusLabel,
  metricPct, metricBandText, metricBandBar, truncate, wordCount,
} from "@/components/pre-sales/utils";

// ── Stepper state derived from gen_status (GET /rfp/packs/{id}/status) ────────
// Steps: Upload -> Parsed -> Assigned -> Drafting -> Review. Upload is always done on entry
// (uploading docs is the prerequisite to being here); the rest are computed from the background
// job's per-artifact progress. See deriveStepper() below.
const IN_FLIGHT: GenState[] = ["pending", "running"];
const isInFlight = (s: GenState | undefined) => s != null && IN_FLIGHT.includes(s);

type StepKey = "upload" | "parsed" | "assigned" | "drafting" | "review";
type StepState = "done" | "active" | "inprogress" | "pending" | "error";
type Phase = "parsing" | "assigned" | "drafting" | "review";
type Step = { key: StepKey; label: string; state: StepState };

function deriveStepper(status: TenderGenStatus, hasSections: boolean) {
  const hasStatus = Object.keys(status).length > 0;
  // Old packs uploaded before the background job carry no gen_status: if their sections already
  // exist (lazily backfilled), everything is done, so land straight on Review.
  const fallback: GenState = hasSections ? "ready" : "pending";
  const reqState: GenState = status.requirements ?? (hasStatus ? "pending" : fallback);
  const secState: GenState = status.sections ?? (hasStatus ? "pending" : fallback);
  const draftsState: GenState = status.drafts?.state ?? (hasStatus ? "pending" : fallback);
  const draftsDone = status.drafts?.done ?? 0;
  const draftsTotal = status.drafts?.total ?? 0;
  const assignmentsConfirmed = status.assignments_confirmed === true;

  const parsedReady = secState === "ready";
  const parsingInFlight = isInFlight(reqState) || isInFlight(secState);
  const parseError = !parsedReady && (secState === "error" || reqState === "error");
  const draftsReady = draftsState === "ready";
  const draftingInFlight = isInFlight(draftsState);

  // The single "phase" drives the tab body (and the active-step highlight).
  const phase: Phase = !parsedReady ? "parsing"
    : !assignmentsConfirmed ? "assigned"
      : !draftsReady ? "drafting"
        : "review";

  const steps: Step[] = [
    { key: "upload", label: "Upload", state: "done" },
    {
      key: "parsed", label: "Parsed",
      state: parsedReady ? "done" : parseError ? "error" : parsingInFlight ? "inprogress" : "pending",
    },
    {
      key: "assigned", label: "Assigned",
      state: !parsedReady ? "pending" : assignmentsConfirmed ? "done" : "active",
    },
    {
      key: "drafting", label: "Drafting",
      state: draftsReady ? "done" : draftingInFlight ? "inprogress" : "pending",
    },
    { key: "review", label: "Review", state: phase === "review" ? "active" : "pending" },
  ];

  return {
    phase, steps, secState, draftsState, draftsReady, parsedReady, draftsDone, draftsTotal,
    pollActive: parsingInFlight || draftingInFlight,
  };
}

export function SectionsTab({ packId }: { packId: string }) {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());

  // gen_status is the source of truth for the stepper; poll it while work is in-flight.
  const statusQ = useQuery({
    queryKey: ["tender-status", packId],
    queryFn: () => getTenderStatus(packId),
    refetchInterval: (q) => {
      const s = q.state.data;
      if (!s) return 3000;
      const parsing = isInFlight(s.requirements) || isInFlight(s.sections);
      const drafting = isInFlight(s.drafts?.state);
      return parsing || drafting ? 3000 : false;
    },
  });
  const sectionsQ = useQuery({ queryKey: ["pack-sections", packId], queryFn: () => listPackSections(packId) });

  const sections = useMemo(() => sectionsQ.data ?? [], [sectionsQ.data]);
  const status = useMemo<TenderGenStatus>(() => statusQ.data ?? {}, [statusQ.data]);
  const stepper = useMemo(() => deriveStepper(status, sections.length > 0), [status, sections.length]);
  const { phase, steps, secState, draftsState, draftsDone, draftsTotal } = stepper;

  const reviewerEditable = phase === "assigned";
  const assigneesQ = useQuery({
    queryKey: ["pack-assignees", packId],
    queryFn: () => getAssignees(packId),
    enabled: reviewerEditable,
  });
  const assignees = useMemo(() => assigneesQ.data ?? [], [assigneesQ.data]);

  const confirm = useMutation({
    mutationFn: () => confirmAssignments(packId),
    onSuccess: (s) => {
      qc.setQueryData(["tender-status", packId], s);
      qc.invalidateQueries({ queryKey: ["tender-status", packId] });
    },
  });

  // Refetch the sections tree on the parse-ready (list appears) and drafts-ready (answers /
  // confidence / grounding appear) transitions the poller catches.
  const prevSec = useRef(secState);
  const prevDrafts = useRef(draftsState);
  useEffect(() => {
    if (prevSec.current !== "ready" && secState === "ready") qc.invalidateQueries({ queryKey: ["pack-sections", packId] });
    prevSec.current = secState;
  }, [secState, packId, qc]);
  useEffect(() => {
    if (prevDrafts.current !== "ready" && draftsState === "ready") {
      qc.invalidateQueries({ queryKey: ["pack-sections", packId] });
      qc.invalidateQueries({ queryKey: ["pack-overview", packId] });
    }
    prevDrafts.current = draftsState;
  }, [draftsState, packId, qc]);

  const allQuestions = useMemo(() => sections.flatMap((s) => s.questions), [sections]);
  const drafted = allQuestions.filter((q) => q.ai_answer || q.user_draft);
  const withConfidence = allQuestions.filter((q) => q.confidence > 0);
  const avgConfidence = withConfidence.length
    ? withConfidence.reduce((n, q) => n + q.confidence, 0) / withConfidence.length
    : 0;

  const selected = selectedId ? sections.find((s) => s.id === selectedId) ?? null : null;
  // Prev/next walk the ordered section list (order_index preserved by the API).
  const selectedIdx = selected ? sections.findIndex((s) => s.id === selected.id) : -1;

  // First load: nothing to derive the stepper from yet.
  if (statusQ.isLoading && sectionsQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2, 3].map((i) => <div key={i} className="h-12 animate-pulse rounded-xl bg-white/[0.04]" />)}</div>;
  }

  // Section detail (Open) -- the full review/editor experience, unchanged.
  if (selected) {
    return (
      <SectionEditor
        packId={packId}
        section={selected}
        canPrev={selectedIdx > 0}
        canNext={selectedIdx >= 0 && selectedIdx < sections.length - 1}
        onPrev={() => setSelectedId(sections[selectedIdx - 1]?.id ?? null)}
        onNext={() => setSelectedId(sections[selectedIdx + 1]?.id ?? null)}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  const topLevel = sections.filter((s) => !s.parent_id);
  const childrenOf = (id: string) => sections.filter((s) => s.parent_id === id);
  const toggleParent = (id: string) => setExpandedParents((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const showTable = phase === "assigned" || phase === "review";

  // "AI-drafted" is counted per TOP-LEVEL SECTION (like idg's "8/15"), NOT per leaf question: a
  // top-level section is drafted when it (childless) or any of its sub-sections has an AI/user draft.
  const sectionIsDrafted = (s: PackSectionNode) => {
    const kids = childrenOf(s.id);
    const qs = kids.length ? kids.flatMap((k) => k.questions) : s.questions;
    return qs.some((q) => q.ai_answer || q.user_draft);
  };
  const sectionsDrafted = topLevel.filter(sectionIsDrafted).length;

  return (
    <div className="space-y-6">
      <OutcomesStrip title="SECTIONS" tiles={[
        { value: `${sectionsDrafted}/${topLevel.length}`, label: "AI-drafted", caption: "grounded, cited", trend: "up" },
        { value: confidencePct(avgConfidence), label: "Avg confidence", caption: "across drafted answers", trend: avgConfidence >= 0.85 ? "up" : avgConfidence >= 0.7 ? "neutral" : "down" },
        { value: confidencePct(avgConfidence), label: "Avg grounding", caption: "KB coverage", trend: avgConfidence >= 0.85 ? "up" : avgConfidence >= 0.7 ? "neutral" : "down" },
      ]} />

      <Stepper steps={steps} />

      {phase === "parsing" ? (
        <ParsingState error={secState === "error"} />
      ) : phase === "drafting" ? (
        <DraftingState done={draftsDone} total={draftsTotal} />
      ) : showTable && topLevel.length === 0 ? (
        <NoSections />
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border border-white/[0.06]">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="w-16 px-4 py-3">#</th>
                  <th className="px-4 py-3">Section</th>
                  <th className="px-4 py-3">Gaps</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Reviewer</th>
                  <th className="w-24 px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {topLevel.map((s) => (
                  <SectionRows
                    key={s.id}
                    packId={packId}
                    section={s}
                    kids={childrenOf(s.id)}
                    expanded={expandedParents.has(s.id)}
                    onToggle={() => toggleParent(s.id)}
                    onOpen={setSelectedId}
                    reviewerEditable={reviewerEditable}
                    assignees={assignees}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {phase === "assigned" && (
            <div className="flex flex-col items-end gap-2">
              <p className="text-[11px] text-slate-500">Assign reviewers to sections, or skip - answers are already drafting in the background.</p>
              <button
                onClick={() => confirm.mutate()}
                disabled={confirm.isPending}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-4 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50"
              >
                {confirm.isPending ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />} Confirm Assignments
              </button>
              {confirm.isError && (
                <p className="flex items-center gap-1.5 text-[11px] text-red-400">
                  <AlertTriangle className="size-3" /> Couldn&apos;t confirm assignments - please try again.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Stepper ──────────────────────────────────────────────────────────────────
const STEP_PILL: Record<StepState, string> = {
  done: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
  active: "border-indigo-500/50 bg-indigo-500/15 text-white",
  inprogress: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  pending: "border-white/10 bg-white/[0.02] text-slate-500",
  error: "border-red-500/40 bg-red-500/10 text-red-400",
};

function StepIcon({ step }: { step: Step }) {
  if (step.state === "done") return <CheckCircle2 className="size-3.5 shrink-0" />;
  if (step.state === "inprogress") return <Loader2 className="size-3.5 shrink-0 animate-spin" />;
  if (step.state === "error") return <AlertTriangle className="size-3.5 shrink-0" />;
  if (step.key === "upload") return <Upload className="size-3.5 shrink-0" />;
  return <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-current" />;
}

function Stepper({ steps }: { steps: Step[] }) {
  return (
    <ol aria-label="Tender progress" className="flex items-center gap-1.5 overflow-x-auto">
      {steps.map((step, i) => (
        <li key={step.key} className="flex flex-1 items-center gap-1.5">
          <div
            aria-current={step.state === "active" ? "step" : undefined}
            className={cn(
              "flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg border px-2.5 py-2 text-[12px] font-semibold",
              STEP_PILL[step.state],
            )}
          >
            <StepIcon step={step} />
            <span className="truncate">{step.label}</span>
          </div>
          {i < steps.length - 1 && <span aria-hidden className="hidden h-px w-3 shrink-0 bg-white/10 sm:block" />}
        </li>
      ))}
    </ol>
  );
}

// ── Body states while the background job runs ────────────────────────────────
function ParsingState({ error }: { error: boolean }) {
  if (error) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-red-500/20 bg-red-500/[0.06] px-4 py-14 text-center">
        <AlertTriangle className="mb-3 size-6 text-red-300" />
        <p className="text-sm font-semibold text-white">Parsing failed</p>
        <p className="mt-1 max-w-sm text-[12px] text-red-300">We couldn&apos;t parse this tender into sections. Try re-uploading it in Sources.</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
      <Loader2 className="mb-3 size-6 animate-spin text-amber-400" />
      <p className="text-sm font-semibold text-white">Parsing the tender into sections{"\u2026"}</p>
      <p className="mt-1 max-w-sm text-[12px] text-slate-500">This runs in the background - the sections list will appear here as soon as it&apos;s ready.</p>
    </div>
  );
}

function DraftingState({ done, total }: { done: number; total: number }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
      <Loader2 className="mb-3 size-6 animate-spin text-amber-400" />
      <p className="text-sm font-semibold text-white">Answers are being generated in the background - you can come back later.</p>
      {total > 0 && <p className="mt-1 text-[12px] text-slate-500">{done}/{total} answers drafted</p>}
    </div>
  );
}

function NoSections() {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-14 text-center">
      <span className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-white/[0.04] text-slate-500">
        <ListChecks className="size-6" />
      </span>
      <p className="text-sm font-semibold text-white">No sections yet</p>
      <p className="mt-1 max-w-sm text-[12px] text-slate-500">Upload the RFP in Sources to parse it into sections and questions.</p>
    </div>
  );
}

// ── Rows ─────────────────────────────────────────────────────────────────────
// A top-level section renders as one clickable row; if it has sub-sections, clicking (or
// Enter/Space) toggles them, and they render as idg-style cards in a full-width row below. Leaf
// sections open straight into the editor. Mirrors idg.qiko.ai's Sections expand experience.
function SectionRows({ packId, section, kids, expanded, onToggle, onOpen, reviewerEditable, assignees }: {
  packId: string; section: PackSectionNode; kids: PackSectionNode[]; expanded: boolean;
  onToggle: () => void; onOpen: (id: string) => void; reviewerEditable: boolean; assignees: Assignee[];
}) {
  const hasKids = kids.length > 0;
  return (
    <>
      <SectionRow packId={packId} section={section} hasKids={hasKids} expanded={expanded}
        onToggle={onToggle} onOpen={onOpen} reviewerEditable={reviewerEditable} assignees={assignees} />
      {hasKids && expanded && (
        <tr className="border-b border-white/[0.04] last:border-0 bg-white/[0.015]">
          <td colSpan={6} className="px-4 pb-3 pt-0.5">
            <div className="ml-6 space-y-2">
              {kids.map((k) => <SubSectionCard key={k.id} section={k} onOpen={onOpen} />)}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function SectionRow({ packId, section, hasKids, expanded, onToggle, onOpen, reviewerEditable, assignees }: {
  packId: string; section: PackSectionNode; hasKids: boolean; expanded: boolean;
  onToggle: () => void; onOpen: (id: string) => void; reviewerEditable: boolean; assignees: Assignee[];
}) {
  const locked = section.questions.filter((q) => q.locked).length;
  // Row activation: parents-with-kids toggle their cards; leaves open the editor.
  const activate = () => (hasKids ? onToggle() : onOpen(section.id));
  return (
    <tr
      role="button"
      tabIndex={0}
      aria-expanded={hasKids ? expanded : undefined}
      aria-label={hasKids
        ? `${section.name}, ${section.subsection_count} sub-section${section.subsection_count > 1 ? "s" : ""}, ${expanded ? "collapse" : "expand"}`
        : `Open ${section.name}`}
      onClick={activate}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); } }}
      className="cursor-pointer border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400/60"
    >
      <td className="px-4 py-3 font-mono text-[12px] text-slate-400">
        <span className="flex items-center gap-1">
          {hasKids
            ? (expanded
              ? <ChevronDown aria-hidden className="size-3.5 text-slate-500" />
              : <ChevronRight aria-hidden className="size-3.5 text-slate-500" />)
            : <span aria-hidden className="inline-block size-3.5" />}
          {section.code || "\u2014"}
        </span>
      </td>
      <td className="px-4 py-3">
        <p className="font-medium text-white">
          {section.name}
          {section.subsection_count > 0 && (
            <span className="ml-2 text-[11px] font-normal text-slate-500">
              ({section.subsection_count} sub-section{section.subsection_count > 1 ? "s" : ""})
            </span>
          )}
        </p>
        <p className="text-[11px] text-slate-500">
          {section.subsection_count > 0
            ? `${section.subsection_count} sub-section${section.subsection_count > 1 ? "s" : ""} to review`
            : `${locked}/${section.questions.length} locked${section.weighting ? ` \u00b7 ${section.weighting}` : ""}`}
        </p>
      </td>
      <td className="px-4 py-3">
        {section.kb_gap ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
            <AlertTriangle className="size-3" /> KB gap
          </span>
        ) : <span className="text-slate-600">{"\u2014"}</span>}
      </td>
      <td className="px-4 py-3">
        <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold", sectionStatusBadgeClass(section.status))}>
          {sectionStatusLabel(section.status)}
        </span>
      </td>
      {/* Reviewer holds its own interactive controls -- keep clicks from bubbling to the row toggle. */}
      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <ReviewerCell packId={packId} section={section} editable={reviewerEditable} assignees={assignees} />
      </td>
      <td className="px-4 py-3 text-right">
        {/* Visual affordance only -- the whole row is the actual button (avoids a duplicate tab stop). */}
        <span
          aria-hidden
          className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[12px] font-medium text-slate-200"
        >
          {hasKids
            ? (<>{expanded ? "Collapse" : "Expand"} {expanded ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}</>)
            : (<>Open <ArrowRight className="size-3" /></>)}
        </span>
      </td>
    </tr>
  );
}

// ── Sub-section card (idg expand experience) ─────────────────────────────────
// Stacked below an expanded parent: code pill + title + conf/grounding bars (%) + optional gaps
// flag + status, with an "Open" action that drops straight into the sub-section's editor.
function SubSectionCard({ section, onOpen }: { section: PackSectionNode; onOpen: (id: string) => void }) {
  const conf = metricPct(section.confidence);
  const grounding = metricPct(section.grounding);
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <span className="shrink-0 rounded-md border border-indigo-500/30 bg-indigo-500/15 px-2 py-0.5 font-mono text-[11px] font-semibold text-indigo-300">
        {section.code || "\u2014"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-white">{section.name}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px]">
          <MetricBar label="conf" pct={conf} />
          <MetricBar label="grounding" pct={grounding} />
          {section.kb_gap && (
            <span className="inline-flex items-center gap-1 font-semibold text-amber-400">
              <AlertTriangle className="size-3" /> gaps
            </span>
          )}
          <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold", sectionStatusBadgeClass(section.status))}>
            {sectionStatusLabel(section.status)}
          </span>
        </div>
      </div>
      <button
        type="button"
        onClick={() => onOpen(section.id)}
        aria-label={`Open ${section.name}`}
        className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[12px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
      >
        Open <ArrowRight className="size-3" />
      </button>
    </div>
  );
}

// One "label bar %" metric inside a sub-section card. Bar + % colour band by the 80/60 thresholds;
// a neutral dash when the metric hasn't been drafted yet.
function MetricBar({ label, pct }: { label: string; pct: number | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-slate-500">{label}</span>
      {pct == null ? (
        <span className="text-slate-600">{"\u2014"}</span>
      ) : (
        <>
          <span className="h-1.5 w-14 overflow-hidden rounded-full bg-white/10">
            <span className={cn("block h-full rounded-full", metricBandBar(pct))} style={{ width: `${pct}%` }} />
          </span>
          <span className={cn("font-semibold tabular-nums", metricBandText(pct))}>{pct}%</span>
        </>
      )}
    </span>
  );
}

// ── Reviewer column ──────────────────────────────────────────────────────────
// Assigned step: editable "Assign" pill -> dropdown of tenant users -> filled "Name x" pill.
// Review step: static read-only pill. Assignment is metadata only (drafts run regardless).
function ReviewerCell({ packId, section, editable, assignees }: {
  packId: string; section: PackSectionNode; editable: boolean; assignees: Assignee[];
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const set = useMutation({
    mutationFn: (v: { reviewer: string | null; name: string }) => setSectionReviewer(packId, section.id, v.reviewer, v.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pack-sections", packId] }),
  });

  const displayName = section.reviewer_name
    || assignees.find((a) => a.id === section.reviewer)?.name
    || (section.reviewer ?? "");
  const hasReviewer = Boolean(section.reviewer || section.reviewer_name);

  // Read-only (Review step).
  if (!editable) {
    return hasReviewer
      ? (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[11px] font-medium text-slate-200">
          <Users className="size-3 text-slate-400" /> {displayName}
        </span>
      )
      : <span className="text-slate-600">{"\u2014"}</span>;
  }

  // Editable (Assigned step).
  return (
    <div className="relative inline-block">
      {hasReviewer ? (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/40 bg-indigo-500/15 px-2.5 py-0.5 text-[11px] font-medium text-white">
          <Users className="size-3 text-indigo-300" /> {displayName}
          <button
            type="button"
            aria-label={`Clear reviewer for ${section.name}`}
            disabled={set.isPending}
            onClick={() => set.mutate({ reviewer: null, name: "" })}
            className="rounded-full text-indigo-200 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50"
          >
            {set.isPending ? <Loader2 className="size-3 animate-spin" /> : <X className="size-3" />}
          </button>
        </span>
      ) : (
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={`Assign reviewer for ${section.name}`}
          disabled={set.isPending}
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-white/25 bg-transparent px-2.5 py-0.5 text-[11px] font-medium text-slate-400 hover:border-indigo-500/40 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50"
        >
          {set.isPending ? <Loader2 className="size-3 animate-spin" /> : <Users className="size-3" />} Assign <ChevronDown className="size-3" />
        </button>
      )}

      {open && !hasReviewer && (
        <>
          {/* click-away overlay */}
          <button type="button" tabIndex={-1} aria-hidden className="fixed inset-0 z-10 cursor-default" onClick={() => setOpen(false)} />
          <ul
            role="listbox"
            aria-label={`Reviewers for ${section.name}`}
            className="absolute left-0 z-20 mt-1 max-h-56 w-52 overflow-y-auto rounded-lg border border-white/10 bg-[#0b0e16] p-1 shadow-xl"
          >
            {assignees.length === 0 ? (
              <li className="px-2.5 py-2 text-[11px] text-slate-500">No teammates to assign.</li>
            ) : assignees.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => { set.mutate({ reviewer: a.id, name: a.name }); setOpen(false); }}
                  className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:bg-white/[0.06]"
                >
                  <Users className="size-3.5 shrink-0 text-slate-400" />
                  <span className="min-w-0 flex-1 truncate">
                    <span className="block truncate">{a.name}</span>
                    {a.email && <span className="block truncate text-[10px] text-slate-500">{a.email}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function SectionEditor({ packId, section, canPrev, canNext, onPrev, onNext, onBack }: {
  packId: string; section: PackSectionNode; canPrev: boolean; canNext: boolean;
  onPrev: () => void; onNext: () => void; onBack: () => void;
}) {
  const qc = useQueryClient();
  const questions = section.questions;
  const lockedCount = questions.filter((q) => q.locked).length;
  const [expandedId, setExpandedId] = useState<string | null>(questions[0]?.id ?? null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["pack-sections", packId] });
    qc.invalidateQueries({ queryKey: ["pack-overview", packId] });
  };

  const lockAll = useMutation({
    mutationFn: () => lockAllInPackSection(packId, section.id),
    onSuccess: invalidate,
  });

  const pct = questions.length ? Math.round((lockedCount / questions.length) * 100) : 0;
  const canLockAll = questions.length > 0 && questions.some((q) => !q.locked) && !section.manual;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-lg px-1 text-[13px] text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
          <ArrowLeft className="size-4" /> All sections
        </button>
        <div className="flex items-center gap-2">
          <button onClick={onPrev} disabled={!canPrev} aria-label="Previous section"
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[12px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-40">
            <ArrowLeft className="size-3.5" /> Prev
          </button>
          <button onClick={onNext} disabled={!canNext} aria-label="Next section"
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[12px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-40">
            Next <ArrowRight className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[12px] text-slate-500">{section.code || "\u2014"}</span>
              <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold", sectionStatusBadgeClass(section.status))}>
                {sectionStatusLabel(section.status)}
              </span>
              {section.kb_gap && (
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                  <AlertTriangle className="size-3" /> KB gap
                </span>
              )}
            </div>
            <h2 className="mt-1.5 text-lg font-semibold text-white">{section.name}</h2>
          </div>
          {canLockAll && (
            <button onClick={() => lockAll.mutate()} disabled={lockAll.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-[12px] font-semibold text-emerald-400 hover:bg-emerald-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/50 disabled:opacity-50">
              {lockAll.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Lock className="size-3.5" />} Lock all
            </button>
          )}
        </div>

        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
            <span>{lockedCount}/{questions.length} locked</span><span>{pct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
      </div>

      {section.manual && (
        <p className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] px-4 py-3 text-[12px] text-amber-300">
          <FileSpreadsheet className="size-4 shrink-0" /> This section requires manual input via the attached spreadsheet -- it isn&apos;t AI-drafted.
        </p>
      )}

      <div className="space-y-3">
        {questions.length === 0 ? (
          <p className="rounded-xl border border-white/[0.06] bg-white/[0.015] px-4 py-8 text-center text-sm text-slate-500">No questions in this section.</p>
        ) : (
          questions.map((q, i) => (
            <QuestionCard
              key={q.id}
              packId={packId}
              question={q}
              index={i + 1}
              manual={section.manual}
              expanded={expandedId === q.id}
              onToggle={() => setExpandedId((cur) => (cur === q.id ? null : q.id))}
              onChanged={invalidate}
            />
          ))
        )}
      </div>
    </div>
  );
}

function QuestionCard({ packId, question, index, manual, expanded, onToggle, onChanged }: {
  packId: string; question: PackQuestion; index: number; manual: boolean;
  expanded: boolean; onToggle: () => void; onChanged: () => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(question.user_draft ?? "");

  const patchCache = (updated: PackQuestion) => {
    qc.setQueryData<PackSectionNode[]>(["pack-sections", packId], (prev) =>
      prev?.map((s) => s.id === updated.section_id
        ? { ...s, questions: s.questions.map((qq) => (qq.id === updated.id ? updated : qq)) }
        : s));
  };

  const regenerate = useMutation({
    mutationFn: () => generatePackQuestion(packId, question.id),
    onSuccess: (u) => { patchCache(u); onChanged(); },
  });
  const save = useMutation({
    mutationFn: () => savePackQuestionDraft(packId, question.id, draft),
    onSuccess: (u) => { patchCache(u); onChanged(); },
  });
  const lock = useMutation({
    mutationFn: () => (question.locked ? unlockPackQuestion(packId, question.id) : lockPackQuestion(packId, question.id)),
    onSuccess: (u) => { patchCache(u); onChanged(); },
  });

  const busy = regenerate.isPending || save.isPending || lock.isPending;
  const words = wordCount(draft);
  const overLimit = question.word_limit != null && words > question.word_limit;

  return (
    <div className={cn("rounded-2xl border bg-white/[0.015]", expanded ? "border-indigo-500/25" : "border-white/[0.06]")}>
      <button onClick={onToggle} aria-expanded={expanded}
        className="flex w-full items-center gap-3 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 focus-visible:ring-inset rounded-2xl">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-white/[0.05] text-[11px] font-bold text-slate-300">Q{index}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-white">{truncate(question.text, 110)}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            {question.word_limit != null && <span>{question.word_limit} words max</span>}
            {question.confidence > 0 && <span className={confidenceClass(question.confidence)}>{confidencePct(question.confidence)} conf.</span>}
            {question.kb_gap && <span className="inline-flex items-center gap-0.5 text-amber-400"><AlertTriangle className="size-3" /> KB gap</span>}
          </span>
        </span>
        {question.locked && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
            <Lock className="size-3" /> Locked
          </span>
        )}
        {expanded ? <ChevronDown className="size-4 shrink-0 text-slate-500" /> : <ChevronRight className="size-4 shrink-0 text-slate-500" />}
      </button>

      {expanded && (
        <div className="border-t border-white/[0.06] p-4">
          <p className="mb-4 text-[13px] leading-relaxed text-slate-300">{question.text}</p>

          {manual ? (
            <p className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] px-4 py-3 text-[12px] text-amber-300">
              <FileSpreadsheet className="size-4 shrink-0" /> This question requires manual input via the attached spreadsheet.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {/* LEFT: grounded AI suggestion */}
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.01] p-3.5">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-violet-300">
                    AI suggestion
                  </span>
                  {question.confidence > 0 && (
                    <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold", confidenceBadgeClass(question.confidence))}>
                      {confidencePct(question.confidence)} grounded
                    </span>
                  )}
                </div>
                <div className="mt-2 min-h-[60px] text-[13px] leading-relaxed text-slate-300">
                  {question.ai_answer ? <AnswerMarkdown text={question.ai_answer} /> : <p className="text-slate-500">Not generated yet.</p>}
                </div>
                {question.ai_sources.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {question.ai_sources.map((src, i) => (
                      <span key={i} className="rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-slate-400">{src}</span>
                    ))}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button onClick={() => setDraft(question.ai_answer)} disabled={!question.ai_answer || question.locked}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[12px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-40">
                    <Copy className="size-3.5" /> Copy to editor
                  </button>
                  <button onClick={() => regenerate.mutate()} disabled={busy || question.locked}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[12px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-40">
                    {regenerate.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Regenerate
                  </button>
                </div>
              </div>

              {/* RIGHT: human editor */}
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.01] p-3.5">
                <div className="flex items-center justify-between">
                  <label htmlFor={`draft-${question.id}`} className="text-[11px] font-semibold uppercase tracking-wider text-indigo-400">Your answer</label>
                  <span className={cn("text-[11px]", overLimit ? "text-red-400" : "text-slate-500")}>
                    {words} word{words === 1 ? "" : "s"}{question.word_limit != null ? ` / ${question.word_limit}` : ""}
                  </span>
                </div>
                <Textarea
                  id={`draft-${question.id}`}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  disabled={question.locked}
                  placeholder={"Write or paste the final answer here\u2026"}
                  className="mt-2 min-h-[140px]"
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  <button onClick={() => save.mutate()} disabled={busy || question.locked}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[12px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-40">
                    {save.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />} Save draft
                  </button>
                  {question.locked ? (
                    <button onClick={() => lock.mutate()} disabled={busy}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[12px] font-semibold text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-40">
                      {lock.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Unlock className="size-3.5" />} Unlock
                    </button>
                  ) : (
                    <button onClick={() => lock.mutate()} disabled={busy || !draft.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-2.5 py-1.5 text-[12px] font-semibold text-white hover:bg-emerald-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 disabled:opacity-40">
                      {lock.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Lock className="size-3.5" />} Lock answer
                    </button>
                  )}
                </div>
                {!draft.trim() && !question.locked && (
                  <p className="mt-2 text-[11px] text-slate-500">Add an answer before locking.</p>
                )}
                {(save.isError || lock.isError || regenerate.isError) && (
                  <p className="mt-2 flex items-center gap-1.5 text-[11px] text-red-400">
                    <AlertTriangle className="size-3" /> Something went wrong — please try again.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
