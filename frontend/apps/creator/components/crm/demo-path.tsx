"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Button, cn } from "@qiko/ui";
import { useCrm } from "@/lib/crm/store";

export const DEMO_STEPS = [
  { n: 1, title: "CRM overview", href: "/crm", hint: "Albemarle is the quiet deal. Reset if the store is mid-demo." },
  { n: 2, title: "Open Albemarle", href: "/crm/companies/albemarle", hint: "Intelligence layer pilot · Maya Chen." },
  { n: 3, title: "Deal context", href: "/crm/companies/albemarle", hint: "Working session, In Discussion, next step still outstanding." },
  { n: 4, title: "Create follow-up", href: "/crm/companies/albemarle", hint: "Run the stall playbook. One owned task. No email send." },
  { n: 5, title: "Creator walls", href: "/studio/intelligence", hint: "Inspect CRM Agent connections. Labelled prototype." },
  { n: 6, title: "Claude draft", href: "/crm/channels?surface=claude", hint: "Ask status, then prepare the follow-up email." },
  { n: 7, title: "Approve in CRM", href: "/crm/companies/albemarle", hint: "Approve send, then confirm the task and timeline." },
  { n: 8, title: "Slack ops", href: "/crm/channels?surface=slack&channel=sales", hint: "Ask Albemarle next steps. No amounts." },
  { n: 9, title: "Channel wall", href: "/crm/channels?surface=slack&channel=sales", hint: "Ask deal value and cost. Expect a refusal." },
  { n: 10, title: "#revenue", href: "/crm/channels?surface=slack&channel=revenue", hint: "Same question as Maya Chen. Values appear." },
  { n: 11, title: "Creator events", href: "/studio/intelligence", hint: "Every allow, block, and approval is in the feed." },
] as const;

export function DemoPath({ compact = false }: { compact?: boolean }) {
  return (
    <Suspense fallback={<div className="h-16 animate-pulse rounded-2xl bg-muted" aria-hidden />}>
      <DemoPathInner compact={compact} />
    </Suspense>
  );
}

function DemoPathInner({ compact }: { compact: boolean }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const crm = useCrm();
  if (!crm.ready) {
    return <div className="h-16 animate-pulse rounded-2xl bg-muted" aria-busy="true" aria-label="Loading demo path" />;
  }
  const current = resolveStep(pathname, params.get("surface"), params.get("channel"), crm);
  const prev = DEMO_STEPS.find((step) => step.n === current.n - 1);
  const next = DEMO_STEPS.find((step) => step.n === current.n + 1);

  return (
    <nav aria-label="Guided demo" className={cn("rounded-2xl border border-border bg-muted/40", compact ? "p-3" : "p-4")}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Leadership demo</p>
          <p className={cn("text-slate-600", compact ? "mt-1 text-[12px]" : "mt-1 text-sm")}>
            Step {current.n} of {DEMO_STEPS.length} · {current.title}
          </p>
          {!compact && <p className="mt-1 text-[12px] text-slate-500">{current.hint}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {prev && (
            <Link href={prev.href} className="inline-flex min-h-11 items-center rounded-lg border border-border px-3 text-sm text-slate-600 hover:text-foreground">
              Previous
            </Link>
          )}
          {next && (
            <Link href={next.href} className="inline-flex min-h-11 items-center rounded-lg bg-slate-100 px-3 text-sm text-foreground hover:bg-white/15">
              Next
            </Link>
          )}
          <Button type="button" size="sm" variant="outline" onClick={crm.reset}>
            Reset demo data
          </Button>
        </div>
      </div>
      <ol className={cn("flex gap-1 overflow-x-auto", compact ? "mt-2" : "mt-3")}>
        {DEMO_STEPS.map((step) => (
          <li key={step.n}>
            <Link
              href={step.href}
              aria-current={step.n === current.n ? "step" : undefined}
              title={`${step.n}. ${step.title}`}
              className={cn(
                "flex min-h-11 min-w-11 items-center justify-center rounded-lg text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                step.n === current.n ? "bg-slate-100 text-foreground" : "text-slate-500 hover:text-foreground",
              )}
            >
              <span className="sr-only">{step.title}</span>
              {step.n}
            </Link>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function resolveStep(
  pathname: string,
  surface: string | null,
  channel: string | null,
  crm: ReturnType<typeof useCrm>,
) {
  const stall = crm.workflowRuns.find((run) => run.id === "stalled")?.status;
  const email = crm.channelRuns.find((run) => run.id === "claude-email")?.status;

  if (pathname.startsWith("/studio/intelligence")) {
    return email === "complete" || crm.channelMessages.some((item) => item.surface === "slack-revenue")
      ? DEMO_STEPS[10]
      : DEMO_STEPS[4];
  }
  if (pathname.startsWith("/crm/channels")) {
    if (channel === "revenue") return DEMO_STEPS[9];
    if (surface === "slack") return DEMO_STEPS[7];
    return email === "complete" ? DEMO_STEPS[6] : DEMO_STEPS[5];
  }
  if (pathname.includes("/companies/albemarle")) {
    if (email === "complete") return DEMO_STEPS[6];
    if (email === "awaiting_approval") return DEMO_STEPS[6];
    if (stall && stall !== "idle") return DEMO_STEPS[3];
    return DEMO_STEPS[1];
  }
  return DEMO_STEPS[0];
}
