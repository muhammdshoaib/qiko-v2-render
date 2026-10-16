"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@qiko/ui";

export const DEMO_STEPS = [
  { n: 1, title: "Pulse", href: "/studio/intelligence", hint: "Start on Pulse: open an insight, then add a human follow-up to the action list." },
  { n: 2, title: "Investors", href: "/studio/intelligence?block=investors", hint: "Investor Concierge Overview — business funnel, evidence-backed insights, honesty labels." },
  { n: 3, title: "Insight", href: "/studio/intelligence?block=investors&worker=intent-intelligence&pane=outcomes&detail=o-referral", hint: "Insight with evidence and recommendation — not an outcome until a person completes it." },
  { n: 4, title: "Action list", href: "/studio/intelligence", hint: "Track follow-ups as To do → In progress → Done. Nothing is auto-executed." },
  { n: 5, title: "Knowledge record", href: "/studio/intelligence?focus=record", hint: "After a human decision, the company record shows what was captured." },
  { n: 6, title: "Analytics", href: "/knowledge/investors?tab=analytics", hint: "CRM-style metrics with Live / Illustrative / Pending integration labels." },
  { n: 7, title: "Portfolio Reporter", href: "/knowledge/portfolio-reporter", hint: "Second knowledge block — holdings to grounded cards, no invented outcomes." },
  { n: 8, title: "Captured activity", href: "/studio/intelligence?tab=observability", hint: "Raw activity stays separate from insights when it adds traceability." },
] as const;

export function DemoGuide() {
  return (
    <Suspense fallback={null}>
      <DemoGuideInner />
    </Suspense>
  );
}

function DemoGuideInner() {
  const pathname = usePathname();
  const router = useRouter();
  const params = useSearchParams();
  if (!pathname.startsWith("/studio")) return null;
  const open = params.get("demo") === "1";
  const step = Number(params.get("step"));
  const current = DEMO_STEPS.find((item) => item.n === (Number.isInteger(step) ? step : resolveStep(pathname, params))) ?? DEMO_STEPS[0];
  const prev = DEMO_STEPS.find((item) => item.n === current.n - 1);
  const next = DEMO_STEPS.find((item) => item.n === current.n + 1);

  if (!open) return null;

  return (
    <nav aria-label="Guided demonstration" className="border-b border-border bg-background px-3 py-3 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Demonstration · {current.n} of {DEMO_STEPS.length}
          </p>
          <p className="mt-1 text-sm text-foreground">{current.title}</p>
          <p className="mt-1 text-[12px] text-slate-400">{current.hint}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {prev ? (
            <Button type="button" size="sm" variant="outline" onClick={() => router.push(withDemo(prev.href, prev.n))}>
              <ChevronLeft className="size-4" /> Previous
            </Button>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled>
              <ChevronLeft className="size-4" /> Previous
            </Button>
          )}
          {next ? (
            <Button type="button" size="sm" onClick={() => router.push(withDemo(next.href, next.n))}>
              Next <ChevronRight className="size-4" />
            </Button>
          ) : (
            <Button type="button" size="sm" disabled>
              Next <ChevronRight className="size-4" />
            </Button>
          )}
          <Link
            href="/studio/intelligence"
            className="inline-flex min-h-11 items-center px-3 text-[13px] text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            Exit
          </Link>
        </div>
      </div>
    </nav>
  );
}

function withDemo(href: string, step: number) {
  return `${href}${href.includes("?") ? "&" : "?"}demo=1&step=${step}`;
}

function resolveStep(pathname: string, params: URLSearchParams) {
  if (pathname.startsWith("/knowledge/portfolio-reporter")) return 7;
  if (pathname.startsWith("/knowledge/investors")) return 6;
  if (params.get("tab") === "observability") return 8;
  if (params.get("focus") === "record") return 5;
  if (params.get("detail") === "o-referral" || params.get("pane") === "outcomes") return 3;
  if (params.get("worker") === "intent-intelligence") return 3;
  if (params.get("block") === "investors") return 2;
  if (pathname.startsWith("/studio/intelligence") || pathname === "/studio") return 1;
  return 1;
}
