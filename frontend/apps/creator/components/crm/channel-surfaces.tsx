"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, cn } from "@qiko/ui";
import { toast } from "sonner";
import { DEMO_USERS, authorize } from "@/lib/crm/policy";
import { useCrm } from "@/lib/crm/store";
import type { ChannelId, ChannelMessage, DemoUserId } from "@/lib/crm/types";
import { PrototypeBadge } from "./prototype-badge";

type Surface = "claude" | "slack";
type SlackChannel = "slack-sales" | "slack-revenue";

export function ChannelSurfacesPage() {
  return (
    <Suspense fallback={<div className="h-48 animate-pulse rounded-2xl bg-muted" aria-busy="true" aria-label="Loading channel surfaces" />}>
      <ChannelSurfacesScreen />
    </Suspense>
  );
}

function ChannelSurfacesScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const [surface, setSurfaceState] = useState<Surface>(params.get("surface") === "slack" ? "slack" : "claude");

  const setSurface = (next: Surface) => {
    setSurfaceState(next);
    const query = new URLSearchParams(params.toString());
    query.set("surface", next);
    router.replace(`/crm/channels?${query.toString()}`, { scroll: false });
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>Channel surfaces</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          The same CRM Agent, the same records. These are labelled walkthroughs — not a signed-in Claude account or a live Slack workspace.
        </p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Surface">
        {([
          { id: "claude" as const, label: "Claude" },
          { id: "slack" as const, label: "Slack" },
        ]).map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={surface === item.id}
            onClick={() => setSurface(item.id)}
            className={cn(
              "min-h-11 rounded-lg px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
              surface === item.id ? "bg-muted text-foreground" : "text-slate-500 hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {surface === "claude" ? <ClaudePanel /> : <SlackPanel />}
    </div>
  );
}

function ClaudePanel() {
  const crm = useCrm();
  const access = authorize("maya", "claude");
  const email = crm.channelRuns.find((run) => run.id === "claude-email");
  const messages = crm.channelMessages.filter((item) => item.surface === "claude");
  const task = crm.tasks.find((item) => item.id === "t-wf-stalled");

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section className="rounded-2xl border border-border bg-muted/40 p-4">
        <Header
          title="Simulated Claude conversation"
          subtitle="Signed-in operator: Maya Chen. Not an Anthropic session."
        />
        <PolicyGate userId="maya" channel="claude" />
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <Button type="button" size="sm" onClick={() => toast.message(crm.askClaudeStatus())}>
            Ask Albemarle status
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => toast.message(crm.askClaudeEmailDraft())}>
            Ask for a follow-up email
          </Button>
        </div>
        <Thread messages={messages} empty="Ask one of the questions above. The agent answers from permitted CRM fields." />
        {crm.emailDraft && (
          <article className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-foreground">Draft for review</h3>
              <PrototypeBadge label="Not sent" />
            </div>
            <p className="mt-2 text-[12px] text-slate-400">To {crm.emailDraft.toName} · {crm.emailDraft.to}</p>
            <p className="mt-1 text-sm text-foreground">{crm.emailDraft.subject}</p>
            <pre className="mt-3 whitespace-pre-wrap text-[13px] leading-relaxed text-slate-600">{crm.emailDraft.body}</pre>
            <p className="mt-3 text-[12px] text-slate-500">
              Approving records the outcome. A draft alone does not close the task.
              {task ? ` Current task: ${task.status === "done" ? "done" : "still open"}.` : ""}
            </p>
            {email?.status === "awaiting_approval" && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button type="button" size="sm" onClick={() => toast.message(crm.approveClaudeEmail())}>
                  Approve send
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => toast.message(crm.holdClaudeEmail())}>
                  Hold
                </Button>
              </div>
            )}
          </article>
        )}
      </section>
      <EffectRail
        access={access}
        crmHref="/crm/companies/albemarle"
        crmEffect={
          email?.status === "complete"
            ? "Albemarle timeline updated. Proposal task closed after approval. Last activity refreshed."
            : crm.emailDraft
              ? "Draft only. CRM task still open. Nothing sent."
              : "No CRM write yet. Status questions are reads."
        }
      />
    </div>
  );
}

function SlackPanel() {
  const crm = useCrm();
  const params = useSearchParams();
  const router = useRouter();
  const [userId, setUserId] = useState<DemoUserId>("maya");
  const [slack, setSlackState] = useState<SlackChannel>(params.get("channel") === "revenue" ? "slack-revenue" : "slack-sales");
  const access = authorize(userId, slack);
  const messages = crm.channelMessages.filter((item) => item.surface === slack);

  const setSlack = (next: SlackChannel) => {
    setSlackState(next);
    const query = new URLSearchParams(params.toString());
    query.set("surface", "slack");
    query.set("channel", next === "slack-revenue" ? "revenue" : "sales");
    router.replace(`/crm/channels?${query.toString()}`, { scroll: false });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section className="rounded-2xl border border-border bg-muted/40 p-4">
        <Header
          title="Simulated Slack channel"
          subtitle="Not a live workspace. Actor and channel both gate the payload."
        />
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <fieldset>
            <legend className="text-[11px] uppercase tracking-wider text-slate-500">Acting as</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {(Object.values(DEMO_USERS)).map((user) => (
                <button
                  key={user.id}
                  type="button"
                  aria-pressed={userId === user.id}
                  onClick={() => setUserId(user.id)}
                  className={cn(
                    "min-h-11 rounded-lg border px-3 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                    userId === user.id ? "border-border bg-slate-100 text-foreground" : "border-border text-slate-400",
                  )}
                >
                  <span className="block">{user.name}</span>
                  <span className="block text-[11px] text-slate-500">{user.role} · finance {user.finance ? "yes" : "no"}</span>
                </button>
              ))}
            </div>
          </fieldset>
          <div className="flex gap-2" role="tablist" aria-label="Slack channel">
            <ChannelTab active={slack === "slack-sales"} onClick={() => setSlack("slack-sales")} label="#sales-pipeline" />
            <ChannelTab active={slack === "slack-revenue"} onClick={() => setSlack("slack-revenue")} label="#revenue" />
          </div>
        </div>
        <PolicyGate userId={userId} channel={slack} />
        <div className="mt-4 flex flex-col gap-2">
          {slack === "slack-sales" ? (
            <>
              <Button type="button" size="sm" onClick={() => toast.message(crm.askSlackSalesOps(userId))}>
                Ask Albemarle next steps
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => toast.message(crm.askSlackSalesFinance(userId))}>
                Ask deal value and delivery cost
              </Button>
            </>
          ) : (
            <>
              <Button type="button" size="sm" onClick={() => toast.message(crm.askSlackRevenueSummary(userId))}>
                Ask upcoming invoices and pipeline value
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => toast.message(crm.askSlackRevenueFinance(userId))}>
                Ask Albemarle value and delivery cost
              </Button>
            </>
          )}
        </div>
        <Thread
          messages={messages}
          empty="Ask a question. Restricted fields are removed before the reply is written."
        />
      </section>
      <EffectRail
        access={access}
        crmHref={slack === "slack-revenue" ? "/crm/invoices" : "/crm/companies/albemarle"}
        crmEffect="Slack answers are reads. Invoice and pipeline figures do not change payment status."
      />
    </div>
  );
}

function Header({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="mt-1 text-[12px] text-slate-400">{subtitle}</p>
      </div>
      <PrototypeBadge label="Simulated integration" />
    </div>
  );
}

function ChannelTab({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "min-h-11 rounded-lg px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
        active ? "bg-muted text-foreground" : "text-slate-500 hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}

function PolicyGate({ userId, channel }: { userId: DemoUserId; channel: ChannelId }) {
  const access = authorize(userId, channel);
  const user = DEMO_USERS[userId];
  return (
    <dl className="mt-4 grid gap-2 rounded-xl border border-border bg-card px-3 py-3 text-[12px] sm:grid-cols-3">
      <div>
        <dt className="text-slate-500">User grant</dt>
        <dd className="mt-0.5 text-slate-700">{user.name} · finance {user.finance ? "allowed" : "denied"}</dd>
      </div>
      <div>
        <dt className="text-slate-500">Channel rule</dt>
        <dd className="mt-0.5 text-slate-700">{channel === "slack-sales" ? "ops only · money blocked" : channel === "slack-revenue" ? "finance if user allowed" : "scoped to signed-in user"}</dd>
      </div>
      <div>
        <dt className="text-slate-500">Combined</dt>
        <dd className={cn("mt-0.5", access.financial ? "text-emerald-300" : "text-amber-300")}>
          {access.financial ? "Financial fields included" : "Financial fields stripped"}
        </dd>
      </div>
    </dl>
  );
}

function Thread({ messages, empty }: { messages: ChannelMessage[]; empty: string }) {
  if (messages.length === 0) {
    return (
      <p className="mt-4 rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-slate-500">
        {empty}
      </p>
    );
  }
  return (
    <ol className="mt-4 space-y-2">
      {messages.map((item) => (
        <li
          key={item.id}
          className={cn(
            "rounded-xl border px-3 py-3 text-sm",
            item.role === "user" && "border-border bg-muted text-slate-700",
            item.role === "agent" && item.outcome === "blocked" && "border-red-500/20 bg-red-500/[0.06] text-slate-100",
            item.role === "agent" && item.outcome !== "blocked" && "border-cyan-500/15 bg-indigo-600/[0.04] text-slate-100",
            item.role === "system" && "border-slate-100 text-slate-400",
          )}
        >
          <p className="text-[11px] uppercase tracking-wider text-slate-500">
            {item.role === "user" ? DEMO_USERS[item.userId].name : item.role === "agent" ? "CRM Agent" : "System"}
            {item.role === "agent" && item.outcome === "blocked" ? " · blocked" : ""}
          </p>
          <p className="mt-1 leading-relaxed">{item.text}</p>
        </li>
      ))}
    </ol>
  );
}

function EffectRail({
  access,
  crmHref,
  crmEffect,
}: {
  access: ReturnType<typeof authorize>;
  crmHref: string;
  crmEffect: string;
}) {
  const crm = useCrm();
  const recent = useMemo(
    () => crm.workflowEvents.filter((item) => item.workflowId.startsWith("claude") || item.workflowId.startsWith("slack")).slice(0, 6),
    [crm.workflowEvents],
  );

  return (
    <aside className="space-y-3">
      <section className="rounded-2xl border border-border bg-muted/40 p-4">
        <h3 className="text-sm font-semibold text-foreground">Effect in CRM</h3>
        <p className="mt-2 text-[13px] text-slate-400">{crmEffect}</p>
        <Link href={crmHref} className="mt-3 inline-block text-[12px] text-indigo-600 hover:underline">Open related record</Link>
      </section>
      <section className="rounded-2xl border border-border bg-muted/40 p-4">
        <h3 className="text-sm font-semibold text-foreground">Creator events</h3>
        {recent.length === 0 ? (
          <p className="mt-2 text-[13px] text-slate-500">No channel events yet.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {recent.map((item) => (
              <li key={item.id}>
                <p className="text-[13px] text-foreground">{item.title}</p>
                <p className="text-[12px] text-slate-500">{item.filter} · {item.detail}</p>
              </li>
            ))}
          </ul>
        )}
        <Link href="/studio/intelligence" className="mt-3 inline-block text-[12px] text-indigo-600 hover:underline">
          View in Creator
        </Link>
      </section>
      <p className="px-1 text-[11px] text-slate-500">
        {access.financial
          ? "This combination may include financial fields."
          : "Restricted fields are deleted from the retrieval payload before the reply is written."}
      </p>
    </aside>
  );
}
