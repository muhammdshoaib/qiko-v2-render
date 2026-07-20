"use client";

// Section Assignment: assign an RFP pack's sections (and their questions) to tenant members, track
// completion, and view a per-member rollup. Wired end to end to qiko-core app.modules.assignments
// (prefix /assignments) via the lib/api client fns. Dark cockpit theme, reusing the shared cockpit
// form controls and @qiko/ui primitives.
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, Loader2, Trash2, Users } from "lucide-react";
import { Badge, cn } from "@qiko/ui";
import {
  assignmentsDashboard, bulkAssign, deleteSectionAssignments, getAssignees, listAssignments,
  listPackSections, sendAssignmentReminder, updateAssignmentStatus,
  type Assignee, type Assignment, type AssignmentDashboardRow, type PackSectionNode, type RfpPack,
} from "@/lib/api";
import { Input, Select } from "@/components/cockpit/controls";
import { formatShortDate } from "@/lib/stringUtils";

export function SectionAssignment({ packs, agentId }: { packs: RfpPack[]; agentId: string }) {
  const qc = useQueryClient();
  const [packId, setPackId] = useState<string>(packs[0]?.id ?? "");
  const activePack = packs.find((p) => p.id === packId) ?? null;

  const sectionsQ = useQuery({
    queryKey: ["assign-sections", packId],
    queryFn: () => listPackSections(packId),
    enabled: !!packId,
  });
  const assigneesQ = useQuery({
    queryKey: ["assign-assignees", packId],
    queryFn: () => getAssignees(packId),
    enabled: !!packId,
  });
  const assignmentsQ = useQuery({
    queryKey: ["assignments", packId],
    queryFn: () => listAssignments({ pack_id: packId }),
    enabled: !!packId,
  });

  const assignees = useMemo<Assignee[]>(() => assigneesQ.data ?? [], [assigneesQ.data]);
  const assigneeName = (id: string) => assignees.find((a) => a.id === id)?.name || id;
  const memberIds = useMemo(() => assignees.map((a) => a.id), [assignees]);

  const dashboardQ = useQuery({
    queryKey: ["assign-dashboard", packId, memberIds],
    queryFn: () => assignmentsDashboard(packId, memberIds),
    enabled: !!packId && memberIds.length > 0,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["assignments", packId] });
    qc.invalidateQueries({ queryKey: ["assign-dashboard", packId] });
  };

  const [error, setError] = useState<string | null>(null);
  const onError = (e: unknown) => setError(e instanceof Error ? e.message : "Something went wrong");

  const assign = useMutation({
    mutationFn: (v: { section: PackSectionNode; assigneeId: string; dueAt: string | null }) =>
      bulkAssign({
        pack_id: packId, agent_id: agentId, rfp_title: activePack?.title ?? null,
        sections: [{
          section_id: v.section.id, assignee_user_id: v.assigneeId,
          questions: v.section.questions.map((q) => q.text),
          title: v.section.name, due_at: v.dueAt,
        }],
      }),
    onSuccess: () => { setError(null); invalidate(); },
    onError,
  });

  const toggleStatus = useMutation({
    mutationFn: (a: Assignment) => updateAssignmentStatus(a.id, a.status === "completed" ? "pending" : "completed"),
    onSuccess: () => { setError(null); invalidate(); },
    onError,
  });

  const removeSection = useMutation({
    mutationFn: (sectionId: string) => deleteSectionAssignments(packId, sectionId),
    onSuccess: () => { setError(null); invalidate(); },
    onError,
  });

  const remind = useMutation({
    mutationFn: (v: { assigneeId?: string; assigneeEmail?: string }) =>
      sendAssignmentReminder({ pack_id: packId, assignee_user_id: v.assigneeId, assignee_email: v.assigneeEmail }),
    onSuccess: () => setError(null),
    onError,
  });

  const assignments = assignmentsQ.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Section Assignment</h2>
          <p className="mt-0.5 text-[13px] text-slate-500">Assign RFP sections to your team and track progress.</p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="assign-pack" className="sr-only">Select RFP</label>
          <Select
            id="assign-pack" wrapperClassName="min-w-[220px]" value={packId}
            onChange={(e) => setPackId(e.target.value)} aria-label="Select RFP"
          >
            {packs.length === 0 && <option value="">No RFPs yet</option>}
            {packs.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
          </Select>
          <button
            type="button"
            onClick={() => remind.mutate({})}
            disabled={!packId || remind.isPending}
            aria-label="Send reminders for this RFP"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50"
          >
            {remind.isPending ? <Loader2 className="size-4 animate-spin" /> : <Bell className="size-4" />}
            Send reminder
          </button>
        </div>
      </div>

      {error && (
        <p className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">
          <AlertTriangle className="size-3.5 shrink-0" /> {error}
        </p>
      )}

      {!packId ? (
        <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-12 text-center">
          <Users className="mb-3 size-8 text-slate-600" />
          <p className="text-sm font-medium text-slate-300">No RFP selected</p>
          <p className="mt-1 max-w-sm text-[12px] text-slate-500">Create a tender first, then assign its sections here.</p>
        </div>
      ) : (
        <>
          {/* Per-member dashboard */}
          <MemberDashboard
            rows={dashboardQ.data ?? []}
            loading={dashboardQ.isLoading}
            assigneeName={assigneeName}
            assigneeEmail={(id) => assignees.find((a) => a.id === id)?.email ?? ""}
            onRemind={(assigneeId, assigneeEmail) => remind.mutate({ assigneeId, assigneeEmail })}
            reminding={remind.isPending}
          />

          {/* Assign a section */}
          <section aria-label="Assign sections" className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
            <h3 className="text-[13px] font-semibold text-white">Assign sections</h3>
            <p className="mt-0.5 text-[12px] text-slate-500">Choose an owner and optional due date, then assign that section&apos;s questions.</p>

            {sectionsQ.isLoading ? (
              <div className="mt-4 space-y-2">
                {[0, 1, 2].map((i) => <div key={i} className="h-12 animate-pulse rounded-lg bg-white/[0.04]" />)}
              </div>
            ) : (sectionsQ.data?.length ?? 0) === 0 ? (
              <p className="mt-4 text-[13px] text-slate-500">No sections parsed for this RFP yet.</p>
            ) : (
              <ul className="mt-4 space-y-2">
                {sectionsQ.data?.map((s) => (
                  <SectionAssignRow
                    key={s.id}
                    section={s}
                    assignees={assignees}
                    onAssign={(assigneeId, dueAt) => assign.mutate({ section: s, assigneeId, dueAt })}
                    pending={assign.isPending}
                  />
                ))}
              </ul>
            )}
          </section>

          {/* Current assignments */}
          <section aria-label="Current assignments" className="rounded-2xl border border-white/[0.06] bg-white/[0.015]">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
              <h3 className="text-[13px] font-semibold text-white">Current assignments</h3>
              <Badge variant="muted">{assignments.length}</Badge>
            </div>
            {assignmentsQ.isLoading ? (
              <div className="space-y-2 p-4">
                {[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-white/[0.04]" />)}
              </div>
            ) : assignments.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-slate-500">No assignments yet for this RFP.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-left">
                  <thead>
                    <tr className="border-b border-white/[0.06] text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      <th scope="col" className="px-4 py-2.5">Section</th>
                      <th scope="col" className="px-4 py-2.5">Question</th>
                      <th scope="col" className="px-4 py-2.5">Assignee</th>
                      <th scope="col" className="px-4 py-2.5">Due</th>
                      <th scope="col" className="px-4 py-2.5">Status</th>
                      <th scope="col" className="px-4 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {assignments.map((a) => (
                      <tr key={a.id} className="hover:bg-white/[0.02]">
                        <td className="px-4 py-2.5 text-[12px] text-slate-200">{a.section_title || "-"}</td>
                        <td className="max-w-[280px] px-4 py-2.5 text-[12px] text-slate-400">
                          <span className="line-clamp-2">{a.question}</span>
                        </td>
                        <td className="px-4 py-2.5 text-[12px] text-slate-300">{assigneeName(a.assignee_user_id)}</td>
                        <td className="px-4 py-2.5 text-[12px] text-slate-400">{formatShortDate(a.due_at)}</td>
                        <td className="px-4 py-2.5">
                          <button
                            type="button"
                            onClick={() => toggleStatus.mutate(a)}
                            disabled={toggleStatus.isPending}
                            aria-label={`Mark ${a.status === "completed" ? "pending" : "completed"}`}
                            className={cn("inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold capitalize transition-colors disabled:opacity-50",
                              a.status === "completed"
                                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                                : "border-amber-500/30 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20")}
                          >
                            {a.status}
                          </button>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {a.section_id && (
                            <button
                              type="button"
                              onClick={() => { if (window.confirm("Remove all assignments for this section?")) removeSection.mutate(a.section_id as string); }}
                              disabled={removeSection.isPending}
                              aria-label={`Delete assignments for ${a.section_title || "section"}`}
                              className="rounded-md p-1.5 text-slate-500 hover:bg-red-500/10 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50 disabled:opacity-50"
                            >
                              <Trash2 className="size-4" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function SectionAssignRow({ section, assignees, onAssign, pending }: {
  section: PackSectionNode;
  assignees: Assignee[];
  onAssign: (assigneeId: string, dueAt: string | null) => void;
  pending: boolean;
}) {
  const [assigneeId, setAssigneeId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const qCount = section.questions.length;

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-slate-200">{section.name}</p>
        <p className="text-[11px] text-slate-500">{qCount} question{qCount === 1 ? "" : "s"}</p>
      </div>
      <label htmlFor={`assignee-${section.id}`} className="sr-only">Assignee for {section.name}</label>
      <Select
        id={`assignee-${section.id}`} wrapperClassName="min-w-[160px]" value={assigneeId}
        onChange={(e) => setAssigneeId(e.target.value)} aria-label={`Assignee for ${section.name}`}
      >
        <option value="">Choose assignee</option>
        {assignees.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
      </Select>
      <label htmlFor={`due-${section.id}`} className="sr-only">Due date for {section.name}</label>
      <Input
        id={`due-${section.id}`} type="date" value={dueAt} onChange={(e) => setDueAt(e.target.value)}
        className="max-w-[150px] [color-scheme:dark]" aria-label={`Due date for ${section.name}`}
      />
      <button
        type="button"
        onClick={() => onAssign(assigneeId, dueAt || null)}
        disabled={!assigneeId || qCount === 0 || pending}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-2 text-[12px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50"
      >
        {pending ? <Loader2 className="size-3.5 animate-spin" /> : null} Assign
      </button>
    </li>
  );
}

function MemberDashboard({ rows, loading, assigneeName, assigneeEmail, onRemind, reminding }: {
  rows: AssignmentDashboardRow[];
  loading: boolean;
  assigneeName: (id: string) => string;
  assigneeEmail: (id: string) => string;
  onRemind: (assigneeId: string, assigneeEmail: string) => void;
  reminding: boolean;
}) {
  const active = rows.filter((r) => r.assigned > 0);

  return (
    <section aria-label="Team progress" className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <h3 className="text-[13px] font-semibold text-white">Team progress</h3>
      <p className="mt-0.5 text-[12px] text-slate-500">Assigned, completed and pending sections per member.</p>

      {loading ? (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {[0, 1].map((i) => <div key={i} className="h-20 animate-pulse rounded-xl bg-white/[0.04]" />)}
        </div>
      ) : active.length === 0 ? (
        <p className="mt-4 text-[13px] text-slate-500">No members have assignments yet.</p>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {active.map((r) => (
            <div key={r.user_id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold text-white">{assigneeName(r.user_id)}</p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {r.completed}/{r.assigned} done &middot; {r.pending} pending
                  </p>
                </div>
                <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                  r.status === "overdue" ? "border-red-500/30 bg-red-500/10 text-red-400"
                    : r.status === "completed" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-400")}>
                  {r.status}
                </span>
              </div>
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
                <div className="h-full rounded-full bg-indigo-400 transition-all" style={{ width: `${Math.min(100, Math.max(0, r.progress))}%` }} />
              </div>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-[11px] text-slate-500">{r.progress}% complete</span>
                {r.pending > 0 && (
                  <button
                    type="button"
                    onClick={() => onRemind(r.user_id, assigneeEmail(r.user_id))}
                    disabled={reminding}
                    className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:bg-white/[0.04] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-50"
                  >
                    <Bell className="size-3" /> Remind
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
