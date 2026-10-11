"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ChevronLeft, ChevronRight, Presentation } from "lucide-react";
import { Button } from "@qiko/ui";

export const DEMO_STEPS = [
  { n: 1, title: "Studio workers", href: "/studio", hint: "Two deployed workers and the outcomes they just delivered." },
  { n: 2, title: "Inspect a worker", href: "/studio/w/property-insights", hint: "Responsibilities, sources, and recent outcomes." },
  { n: 3, title: "Company record", href: "/studio/intelligence?focus=record", hint: "The same outcomes land on company intelligence." },
  { n: 4, title: "Connections", href: "/studio/intelligence?focus=intent-intelligence", hint: "What the Intelligence Worker may read, write, and must not do." },
  { n: 5, title: "Ask Claude", href: "/studio/intelligence?tab=channels&surface=claude", hint: "Ask Property Insights for a grounded portfolio insight." },
  { n: 6, title: "Approve a follow-up", href: "/studio/intelligence?tab=channels&surface=claude", hint: "Recommend a Lombay review. Approve it. Nothing is sent outbound." },
  { n: 7, title: "Slack walls", href: "/studio/intelligence?tab=channels&surface=slack", hint: "Ask the same spend question in both channels, then as an unauthorised user." },
  { n: 8, title: "Captured activity", href: "/studio/intelligence?tab=observability", hint: "Allowed, blocked, and approved actions in one feed." },
  { n: 9, title: "Intelligence layer", href: "/studio/intelligence?focus=record", hint: "Recorded decisions grow the company record." },
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

  if (!open) {
    return (
      <div className="flex justify-end border-b border-white/[0.04] px-3 py-1 sm:px-6">
        <Link
          href={`${DEMO_STEPS[0].href}${DEMO_STEPS[0].href.includes("?") ? "&" : "?"}demo=1&step=1`}
          className="inline-flex min-h-11 items-center gap-2 px-2 text-[13px] text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        >
          <Presentation className="size-4" /> Present
        </Link>
      </div>
    );
  }

  return (
    <nav aria-label="Guided demonstration" className="border-b border-white/[0.06] bg-[#05070d] px-3 py-3 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Demonstration · {current.n} of {DEMO_STEPS.length}
          </p>
          <p className="mt-1 text-sm text-white">{current.title}</p>
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
            href={pathname.startsWith("/studio/intelligence") ? "/studio/intelligence" : "/studio"}
            className="inline-flex min-h-11 items-center px-3 text-[13px] text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
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
  if (pathname === "/studio") return 1;
  if (pathname.startsWith("/studio/w/")) return 2;
  if (params.get("tab") === "channels" && params.get("surface") === "slack") return 7;
  if (params.get("tab") === "channels") return 5;
  if (params.get("tab") === "observability") return 8;
  if (params.get("focus") === "intent-intelligence") return 4;
  if (params.get("focus") === "record") return 3;
  if (pathname.startsWith("/studio/intelligence")) return 3;
  return 1;
}
