"use client";

import Link from "next/link";
import { Button, cn } from "@qiko/ui";
import { toast } from "sonner";
import { useCrm } from "@/lib/crm/store";
import { runLabel } from "@/lib/crm/workflows";
import { PrototypeBadge } from "./prototype-badge";
import { CompleteTaskButton } from "./complete-task-button";
import { WORKFLOW_IDS } from "@/lib/crm/workflows";

const PLAYBOOKS = [
  {
    id: "stalled" as const,
    title: "A · Stalled opportunity",
    company: "Albemarle",
    href: "/crm/companies/albemarle",
    steps: [
      { key: "detect", label: "Detect quiet period" },
      { key: "task", label: "Create follow-up task" },
      { key: "slack", label: "Notify #sales-pipeline" },
      { key: "email", label: "Claude email approved" },
      { key: "record", label: "CRM last activity updates" },
    ],
    startLabel: "Create follow-up task",
  },
  {
    id: "meeting" as const,
    title: "B · Meeting outcome",
    company: "Harrow Street Partners",
    href: "/crm/companies/harrow",
    steps: [
      { key: "notes", label: "Record meeting note" },
      { key: "tasks", label: "Create tasks from the note" },
      { key: "proposed", label: "Propose Confirmed" },
      { key: "approved", label: "Owner approves" },
      { key: "updated", label: "Stage updates" },
    ],
    startLabel: "Process meeting note",
  },
  {
    id: "invoice" as const,
    title: "C · Invoice due",
    company: "Lumen Court Residences",
    href: "/crm/invoices",
    steps: [
      { key: "due", label: "Detect due invoice" },
      { key: "revenue", label: "Alert #revenue" },
      { key: "task", label: "Create collection task" },
    ],
    startLabel: "Run invoice monitor",
  },
];

export function WorkflowLab() {
  const crm = useCrm();

  return (
    <section aria-labelledby="workflow-lab-title" className="rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.04] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="workflow-lab-title" className="text-sm font-semibold text-white">CRM Agent playbooks</h2>
          <p className="mt-1 text-[13px] text-slate-400">
            Clickable prototype of three worker outcomes. Each step writes the same events Creator reads.
          </p>
        </div>
        <PrototypeBadge label="Agent · prototype" />
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        {PLAYBOOKS.map((playbook) => {
          const run = crm.workflowRuns.find((item) => item.id === playbook.id);
          const status = run?.status ?? "idle";
          return (
            <article key={playbook.id} className="flex flex-col rounded-xl border border-white/[0.06] bg-[#070a12] p-4">
              <p className="text-[11px] uppercase tracking-wider text-slate-500">{runLabel(playbook.id)}</p>
              <h3 className="mt-1 text-sm font-semibold text-white">{playbook.title}</h3>
              <Link href={playbook.href} className="mt-1 text-[12px] text-indigo-300 hover:underline">{playbook.company}</Link>
              <ol className="mt-3 space-y-1.5 text-[12px] text-slate-400">
                {playbook.steps.map((step) => {
                  const done = run?.completedSteps.includes(step.key) ?? false;
                  return (
                    <li key={step.key} className={cn("flex gap-2", done && "text-slate-200")}>
                      <span className={cn("mt-0.5 size-1.5 shrink-0 rounded-full", done ? "bg-cyan-300" : "bg-white/20")} />
                      {step.label}
                    </li>
                  );
                })}
              </ol>
              <p className="mt-3 text-[11px] capitalize text-slate-500">{status.replaceAll("_", " ")}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {playbook.id === "stalled" && status === "idle" && (
                  <Button type="button" size="sm" onClick={() => toast.message(crm.runStalledWorkflow())}>{playbook.startLabel}</Button>
                )}
                {playbook.id === "stalled" && status === "awaiting_owner" && (
                  <CompleteTaskButton taskId={WORKFLOW_IDS.stalledTask} />
                )}
                {playbook.id === "meeting" && status === "idle" && (
                  <Button type="button" size="sm" onClick={() => toast.message(crm.runMeetingWorkflow())}>{playbook.startLabel}</Button>
                )}
                {playbook.id === "meeting" && status === "awaiting_approval" && (
                  <Button type="button" size="sm" onClick={() => toast.message(crm.approveMeetingStage())}>Approve stage change</Button>
                )}
                {playbook.id === "invoice" && status === "idle" && (
                  <Button type="button" size="sm" onClick={() => toast.message(crm.runInvoiceWorkflow())}>{playbook.startLabel}</Button>
                )}
                {status === "complete" && (
                  <span className="text-[12px] text-emerald-300">Playbook complete</span>
                )}
                <Link href="/studio/intelligence" className="text-[12px] text-slate-400 underline-offset-2 hover:text-white hover:underline">
                  View in Creator
                </Link>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
