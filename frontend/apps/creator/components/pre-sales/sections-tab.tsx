"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ChevronDown, ChevronRight, Lock, Unlock, Loader2, RefreshCw, Copy, Save,
  ArrowLeft, ArrowRight, FileSpreadsheet, ListChecks, CheckCircle2,
} from "lucide-react";
import { cn } from "@qiko/ui";
import {
  getRfpPack, listPackSections, setPackStage, generatePackQuestion, savePackQuestionDraft,
  lockPackQuestion, unlockPackQuestion, lockAllInPackSection,
  type PackSectionNode, type PackQuestion, type PackStage,
} from "@/lib/api";
import { AnswerMarkdown } from "@/components/chat-message";
import {
  confidenceBadgeClass, confidenceClass, confidencePct, sectionStatusBadgeClass, sectionStatusLabel,
  STAGE_LABELS, STAGE_ORDER, truncate, wordCount,
} from "@/components/pre-sales/utils";

export function SectionsTab({ packId }: { packId: string }) {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());

  const sectionsQ = useQuery({ queryKey: ["pack-sections", packId], queryFn: () => listPackSections(packId) });
  const packQ = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });

  const sections = useMemo(() => sectionsQ.data ?? [], [sectionsQ.data]);
  const stage = (packQ.data?.stage ?? "parsed") as PackStage;

  const setStage = useMutation({
    mutationFn: (s: PackStage) => setPackStage(packId, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rfp-pack", packId] }),
  });

  const allQuestions = useMemo(() => sections.flatMap((s) => s.questions), [sections]);
  const drafted = allQuestions.filter((q) => q.ai_answer || q.user_draft);
  const withConfidence = allQuestions.filter((q) => q.confidence > 0);
  const avgConfidence = withConfidence.length
    ? withConfidence.reduce((n, q) => n + q.confidence, 0) / withConfidence.length
    : 0;

  const selected = selectedId ? sections.find((s) => s.id === selectedId) ?? null : null;
  // Prev/next walk the ordered section list (order_index preserved by the API).
  const selectedIdx = selected ? sections.findIndex((s) => s.id === selected.id) : -1;

  if (sectionsQ.isLoading) {
    return <div className="space-y-3">{[0, 1, 2, 3].map((i) => <div key={i} className="h-12 animate-pulse rounded-xl bg-white/[0.04]" />)}</div>;
  }
  if (sectionsQ.isError) {
    return (
      <p className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
        <AlertTriangle className="size-4 shrink-0" /> Couldn&apos;t load sections. Try refreshing.
      </p>
    );
  }
  if (sections.length === 0) {
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-white/[0.06] bg-white/[0.015] px-5 py-4">
        <Stat label="AI-drafted" value={`${drafted.length}/${allQuestions.length}`} />
        <span className="hidden h-8 w-px bg-white/10 sm:block" />
        <Stat label="Avg confidence" value={confidencePct(avgConfidence)} valueClass={confidenceClass(avgConfidence)} />
        <span className="hidden h-8 w-px bg-white/10 sm:block" />
        <Stat label="Avg grounding" value={confidencePct(avgConfidence)} valueClass={confidenceClass(avgConfidence)} />
      </div>

      <StageBar stage={stage} onSet={(s) => setStage.mutate(s)} pending={setStage.isPending} error={setStage.isError} />

      <div className="overflow-x-auto rounded-2xl border border-white/[0.06]">
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wider text-slate-500">
              <th className="w-16 px-4 py-3">#</th>
              <th className="px-4 py-3">Section</th>
              <th className="px-4 py-3">Gaps</th>
              <th className="px-4 py-3">Status</th>
              <th className="w-24 px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {topLevel.map((s) => {
              const kids = childrenOf(s.id);
              const expanded = expandedParents.has(s.id);
              return (
                <SectionRows
                  key={s.id}
                  section={s}
                  kids={kids}
                  expanded={expanded}
                  onToggle={() => setExpandedParents((prev) => {
                    const next = new Set(prev);
                    if (next.has(s.id)) next.delete(s.id); else next.add(s.id);
                    return next;
                  })}
                  onOpen={setSelectedId}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={cn("text-lg font-bold text-white", valueClass)}>{value}</p>
    </div>
  );
}

function StageBar({ stage, onSet, pending, error }: {
  stage: PackStage; onSet: (s: PackStage) => void; pending: boolean; error: boolean;
}) {
  const currentIdx = STAGE_ORDER.indexOf(stage);
  return (
    <div>
      <div className="flex items-center gap-1.5 overflow-x-auto">
        {STAGE_ORDER.map((s, i) => {
          const done = i < currentIdx;
          const current = i === currentIdx;
          return (
            <div key={s} className="flex flex-1 items-center gap-1.5">
              <button
                onClick={() => onSet(s)}
                disabled={pending || current}
                aria-current={current ? "step" : undefined}
                className={cn(
                  "flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg border px-2.5 py-2 text-[12px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:cursor-default",
                  done && "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/15",
                  current && "border-indigo-500/40 bg-indigo-500/15 text-white",
                  !done && !current && "border-white/10 bg-white/[0.02] text-slate-500 hover:text-slate-300",
                )}
              >
                {done && <CheckCircle2 className="size-3.5 shrink-0" />}
                <span className="truncate">{STAGE_LABELS[s]}</span>
              </button>
              {i < STAGE_ORDER.length - 1 && <span className="hidden h-px w-3 shrink-0 bg-white/10 sm:block" />}
            </div>
          );
        })}
      </div>
      {error && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-400">
          <AlertTriangle className="size-3.5" /> Couldn&apos;t change stage. A pack can only be finalised once every section is locked.
        </p>
      )}
    </div>
  );
}

function SectionRows({ section, kids, expanded, onToggle, onOpen }: {
  section: PackSectionNode; kids: PackSectionNode[]; expanded: boolean; onToggle: () => void; onOpen: (id: string) => void;
}) {
  return (
    <>
      <SectionRow section={section} depth={0} hasKids={kids.length > 0} expanded={expanded} onToggle={onToggle} onOpen={onOpen} />
      {expanded && kids.map((k) => (
        <SectionRow key={k.id} section={k} depth={1} hasKids={false} expanded={false} onToggle={() => {}} onOpen={onOpen} />
      ))}
    </>
  );
}

function SectionRow({ section, depth, hasKids, expanded, onToggle, onOpen }: {
  section: PackSectionNode; depth: number; hasKids: boolean; expanded: boolean; onToggle: () => void; onOpen: (id: string) => void;
}) {
  const locked = section.questions.filter((q) => q.locked).length;
  return (
    <tr className={cn("border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02]", depth > 0 && "bg-white/[0.01]")}>
      <td className="px-4 py-3 font-mono text-[12px] text-slate-400">
        <span className="flex items-center gap-1" style={{ paddingLeft: depth * 14 }}>
          {hasKids ? (
            <button onClick={onToggle} aria-label={expanded ? "Collapse sub-sections" : "Expand sub-sections"} aria-expanded={expanded}
              className="rounded text-slate-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
              {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
            </button>
          ) : <span className="inline-block size-3.5" />}
          {section.code || "\u2014"}
        </span>
      </td>
      <td className="px-4 py-3">
        <p className="font-medium text-white">{section.name}</p>
        <p className="text-[11px] text-slate-500">{locked}/{section.questions.length} locked{section.weighting ? ` \u00b7 ${section.weighting}` : ""}</p>
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
      <td className="px-4 py-3 text-right">
        <button onClick={() => onOpen(section.id)}
          className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[12px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
          Open <ArrowRight className="size-3" />
        </button>
      </td>
    </tr>
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
                <textarea
                  id={`draft-${question.id}`}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  disabled={question.locked}
                  placeholder={"Write or paste the final answer here\u2026"}
                  className="mt-2 min-h-[140px] w-full resize-y rounded-lg border border-white/10 bg-white/[0.02] p-3 text-[13px] leading-relaxed text-white placeholder:text-slate-500 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/40 disabled:opacity-60"
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
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
