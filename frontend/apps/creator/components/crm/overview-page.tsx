"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Clock } from "lucide-react";
import { Button } from "@qiko/ui";
import { formatDate, formatMoney, timeSince } from "@/lib/crm/format";
import { useCrm } from "@/lib/crm/store";
import { AgentStrip } from "./agent-strip";
import { PrototypeBadge } from "./prototype-badge";
import { WorkflowLab } from "./workflow-lab";

export function CrmOverviewPage() {
  const crm = useCrm();
  const customers = crm.opportunities.filter((item) => item.stage === "confirmed" || item.stage === "charged");
  const openOpps = crm.opportunities.filter((item) => item.stage !== "charged");
  const pipelineValue = openOpps.reduce((sum, item) => sum + item.value, 0);
  const expected = openOpps.reduce((sum, item) => sum + item.expectedRevenue, 0);
  const outstanding = crm.invoices.filter((item) => item.status !== "paid");
  const outstandingValue = outstanding.reduce((sum, item) => sum + (item.amount - item.paidAmount), 0);
  const openTasks = crm.tasks.filter((item) => item.status === "open");
  const overdue = openTasks.filter((item) => new Date(item.dueDate).getTime() < Date.now());
  const upcoming = openTasks.filter((item) => new Date(item.dueDate).getTime() >= Date.now()).slice(0, 5);
  const attention = crm.opportunities.filter((item) => {
    const quiet = Date.now() - new Date(item.lastActivityAt).getTime() > 7 * 86_400_000;
    return quiet && item.stage !== "charged";
  });

  const tiles = [
    { label: "Active customers", value: String(customers.length), href: "/crm/pipeline" },
    { label: "Open opportunities", value: String(openOpps.length), href: "/crm/pipeline" },
    { label: "Pipeline value", value: formatMoney(pipelineValue), href: "/crm/pipeline" },
    { label: "Expected revenue", value: formatMoney(expected), href: "/crm/pipeline" },
    { label: "Outstanding invoices", value: formatMoney(outstandingValue), href: "/crm/invoices" },
  ];

  return (
    <div className="space-y-6">
      <WorkflowLab />
      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-white">Claude and Slack</h2>
            <p className="mt-1 text-[13px] text-slate-400">Same agent, channel and user walls. Simulated walkthroughs — not live accounts.</p>
          </div>
          <Link href="/crm/channels" className="text-sm text-indigo-300 hover:underline">Open channel surfaces</Link>
        </div>
      </section>
      <AgentStrip />
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {tiles.map((tile) => (
          <Link key={tile.label} href={tile.href} className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4 hover:border-indigo-500/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
            <p className="text-2xl font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{tile.value}</p>
            <p className="mt-1 text-xs text-slate-400">{tile.label}</p>
          </Link>
        ))}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Deals requiring attention" action={<Link href="/crm/pipeline" className="text-sm text-indigo-300">Open pipeline</Link>}>
          {attention.length === 0 ? (
            <Empty text="No stalled open deals." />
          ) : (
            <ul className="divide-y divide-white/[0.05]">
              {attention.map((opp) => {
                const company = crm.companyById(opp.companyId);
                return (
                  <li key={opp.id} className="flex items-center justify-between gap-3 py-3">
                    <div>
                      <Link href={`/crm/companies/${opp.companyId}`} className="text-sm font-medium text-white hover:underline">{company?.name}</Link>
                      <p className="text-xs text-amber-300"><AlertTriangle className="mr-1 inline size-3" />Quiet {timeSince(opp.lastActivityAt)} · {opp.nextStep}</p>
                    </div>
                    <span className="text-sm text-slate-300">{formatMoney(opp.value)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Upcoming and overdue tasks" action={<Link href="/crm/tasks" className="text-sm text-indigo-300">All tasks</Link>}>
          {openTasks.length === 0 ? (
            <Empty text="No open tasks." />
          ) : (
            <ul className="space-y-2">
              {overdue.map((task) => (
                <TaskRow key={task.id} title={task.title} meta={`${crm.companyById(task.companyId)?.name} · overdue ${formatDate(task.dueDate)}`} tone="text-red-300" href={`/crm/companies/${task.companyId}`} />
              ))}
              {upcoming.map((task) => (
                <TaskRow key={task.id} title={task.title} meta={`${crm.companyById(task.companyId)?.name} · ${formatDate(task.dueDate)}`} tone="text-slate-400" href={`/crm/companies/${task.companyId}`} />
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Recent CRM and agent activity">
        {crm.activities.length === 0 ? (
          <Empty text="No activity yet." />
        ) : (
          <ul className="divide-y divide-white/[0.05]">
            {crm.activities.slice(0, 8).map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-3 py-3">
                <div>
                  <p className="text-sm text-white">{item.title}</p>
                  <p className="text-xs text-slate-400">{item.detail}</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  {item.kind === "agent" && <PrototypeBadge label="Agent" tone="default" />}
                  <span className="text-xs text-slate-500">{timeSince(item.at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="flex flex-wrap gap-2">
        <Link href="/crm/pipeline"><Button type="button">Move a deal <ArrowRight className="size-4" /></Button></Link>
        <Link href="/crm/tasks"><Button type="button" variant="outline">Clear overdue tasks</Button></Link>
        <Link href="/crm/invoices"><Button type="button" variant="outline">Review invoices</Button></Link>
      </div>
    </div>
  );
}

function Card({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-white">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-6 text-sm text-slate-400">{text}</p>;
}

function TaskRow({ title, meta, tone, href }: { title: string; meta: string; tone: string; href: string }) {
  return (
    <li>
      <Link href={href} className="block rounded-lg px-1 py-1.5 hover:bg-white/[0.03]">
        <p className="text-sm text-white">{title}</p>
        <p className={`text-xs ${tone}`}><Clock className="mr-1 inline size-3" />{meta}</p>
      </Link>
    </li>
  );
}
