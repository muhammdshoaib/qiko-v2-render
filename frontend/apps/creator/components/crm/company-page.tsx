"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { Button, Input } from "@qiko/ui";
import { formatDate, formatMoney, invoiceTone, stageLabel, timeSince } from "@/lib/crm/format";
import { useCrm } from "@/lib/crm/store";
import { toast } from "sonner";
import { AgentStrip } from "./agent-strip";
import { OpportunityDialog } from "./opportunity-dialog";
import { PrototypeBadge } from "./prototype-badge";
import { CompleteTaskButton } from "./complete-task-button";

export function CrmCompanyPage({ companyId }: { companyId: string }) {
  const crm = useCrm();
  const company = crm.companyById(companyId);
  const [note, setNote] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  if (!company) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 px-6 py-16 text-center">
        <p className="text-sm text-white">This company is not in the sample set.</p>
        <Link href="/crm/pipeline" className="mt-3 inline-block text-sm text-indigo-300">Back to pipeline</Link>
      </div>
    );
  }

  const contacts = crm.contacts.filter((item) => item.companyId === companyId);
  const opps = crm.opportunities.filter((item) => item.companyId === companyId);
  const invoices = crm.invoices.filter((item) => item.companyId === companyId);
  const commitments = crm.commitments.filter((item) => item.companyId === companyId);
  const tasks = crm.tasks.filter((item) => item.companyId === companyId);
  const activities = crm.activities.filter((item) => item.companyId === companyId);
  const editing = opps.find((item) => item.id === editingId) ?? null;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/crm/pipeline" className="text-sm text-slate-400 hover:text-white">← Pipeline</Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{company.name}</h2>
            <p className="text-sm text-slate-400">{company.sector} · {company.location} · Owner {company.owner}</p>
          </div>
          <PrototypeBadge />
        </div>
        <p className="mt-3 max-w-3xl text-sm text-slate-300">{company.summary}</p>
      </div>

      {companyId === "harrow" && crm.workflowRuns.find((run) => run.id === "meeting")?.status === "idle" && (
        <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.04] p-4">
          <p className="text-sm text-white">Recorded note: proposal directionally accepted, pending payment terms.</p>
          <Button type="button" size="sm" className="mt-3" onClick={() => toast.message(crm.runMeetingWorkflow())}>
            Process meeting outcome
          </Button>
        </div>
      )}
      {companyId === "harrow" && crm.workflowRuns.find((run) => run.id === "meeting")?.status === "awaiting_approval" && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.06] p-4">
          <p className="text-sm text-white">Stage change proposed: Negotiation → Confirmed.</p>
          <Button type="button" size="sm" className="mt-3" onClick={() => toast.message(crm.approveMeetingStage())}>
            Approve stage change
          </Button>
        </div>
      )}
      {companyId === "albemarle" && crm.workflowRuns.find((run) => run.id === "stalled")?.status === "awaiting_owner" && crm.channelRuns.find((run) => run.id === "claude-email")?.status !== "complete" && (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
          <p className="text-sm text-white">Follow-up task is open. Prepare the email in the Claude walkthrough — a draft will not close it.</p>
          <Link href="/crm/channels?surface=claude" className="mt-3 inline-flex min-h-11 items-center text-sm text-indigo-300 hover:underline">
            Continue in Claude
          </Link>
        </div>
      )}
      {companyId === "albemarle" && crm.channelRuns.find((run) => run.id === "claude-email")?.status === "awaiting_approval" && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.06] p-4">
          <p className="text-sm text-white">A follow-up draft is waiting in the Claude walkthrough. The proposal task stays open until it is approved.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" size="sm" onClick={() => toast.message(crm.approveClaudeEmail())}>Approve send</Button>
            <Link href="/crm/channels?surface=claude" className="inline-flex min-h-9 items-center text-sm text-indigo-300 hover:underline">Review draft</Link>
          </div>
        </div>
      )}
      {companyId === "albemarle" && crm.workflowRuns.find((run) => run.id === "stalled")?.status === "idle" && (
        <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.04] p-4">
          <p className="text-sm text-white">No meaningful activity for 8 days. The agent can create one follow-up task.</p>
          <Button type="button" size="sm" className="mt-3" onClick={() => toast.message(crm.runStalledWorkflow())}>
            Create follow-up task
          </Button>
        </div>
      )}
      <AgentStrip companyId={companyId} />

      <Section title="Key contacts">
        {contacts.length === 0 ? <Empty text="No contacts on file." /> : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {contacts.map((contact) => (
              <li key={contact.id} className="rounded-xl border border-white/[0.05] px-3 py-3">
                <p className="text-sm text-white">{contact.name}</p>
                <p className="text-xs text-slate-400">{contact.role}</p>
                <p className="mt-1 text-xs text-slate-500">{contact.email} · {contact.phone}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Opportunity history">
        {opps.length === 0 ? <Empty text="No opportunities yet." /> : (
          <ul className="divide-y divide-white/[0.05]">
            {opps.map((opp) => (
              <li key={opp.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm text-white">{opp.title}</p>
                  <p className="text-xs text-slate-400">{stageLabel(opp.stage)} · {formatMoney(opp.value)} · {timeSince(opp.lastActivityAt)}</p>
                </div>
                <Button type="button" size="sm" variant="outline" onClick={() => setEditingId(opp.id)}>Edit</Button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Follow-up tasks">
        {tasks.length === 0 ? <Empty text="No tasks for this company." /> : (
          <ul className="space-y-2">
            {tasks.map((task) => (
              <li key={task.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.05] px-3 py-2">
                <div>
                  <p className="text-sm text-white">{task.title}</p>
                  <p className="text-xs text-slate-400">{task.owner} · {formatDate(task.dueDate)} · {task.source}</p>
                </div>
                {task.status === "open" ? (
                  <CompleteTaskButton taskId={task.id} />
                ) : <span className="text-xs text-emerald-300">Done</span>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Commercial commitments and invoices">
        {commitments.map((item) => (
          <p key={item.id} className="text-sm text-slate-300">{item.title} · {item.cadence} · {formatMoney(item.amount)} · next {formatDate(item.nextDate)}</p>
        ))}
        {invoices.length === 0 ? <Empty text="No invoices linked." /> : (
          <ul className="mt-3 divide-y divide-white/[0.05]">
            {invoices.map((invoice) => (
              <li key={invoice.id} className="flex justify-between py-2 text-sm">
                <span className="text-white">{invoice.number}</span>
                <span className={invoiceTone(invoice.status)}>{formatMoney(invoice.amount)} · {invoice.status}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Notes and meeting outcomes">
        <form
          className="mb-4 flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (!note.trim()) {
              toast.error("Write a note first.");
              return;
            }
            crm.addNote(companyId, opps[0]?.id ?? null, note.trim());
            setNote("");
            toast.success("Note added to the timeline.");
          }}
        >
          <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a meeting outcome or note" />
          <Button type="submit">Add note</Button>
        </form>
        <ol className="space-y-3">
          {activities.length === 0 ? <Empty text="No timeline events yet." /> : activities.map((item) => (
            <li key={item.id} className="rounded-xl border border-white/[0.05] px-3 py-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm text-white">{item.title}</p>
                <div className="flex items-center gap-2">
                  {item.kind === "agent" && <PrototypeBadge label="Agent suggestion / mock" tone="default" />}
                  {item.kind === "human" && <span className="text-[10px] uppercase tracking-wide text-slate-500">Completed</span>}
                  <span className="text-xs text-slate-500">{timeSince(item.at)}</span>
                </div>
              </div>
              <p className="mt-1 text-sm text-slate-400">{item.detail}</p>
            </li>
          ))}
        </ol>
      </Section>

      {editing && <OpportunityDialog key={editing.id} open onOpenChange={(open) => !open && setEditingId(null)} initial={editing} />}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
      <h3 className="mb-3 text-sm font-semibold text-white">{title}</h3>
      {children}
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-sm text-slate-400">{text}</p>;
}
