"use client";

import { ChevronLeft, ChevronRight, Presentation } from "lucide-react";
import { Button, cn } from "@qiko/ui";
import type { ActivityFilter, FocusId } from "./model";

export type PresentationPatch = {
  focus?: FocusId | null;
  edge?: string | null;
  activity?: ActivityFilter;
  event?: string | null;
  replay?: boolean;
  present?: boolean;
  step?: number | null;
};

export const PRESENTATION_STEPS: {
  n: number;
  title: string;
  hint: string;
  patch: PresentationPatch;
}[] = [
  {
    n: 1,
    title: "Company record",
    hint: "Qiko’s shared memory sits at the centre. Rings are captured outcomes over time.",
    patch: { focus: "record", edge: null, event: null, activity: "all", replay: false },
  },
  {
    n: 2,
    title: "Two workers",
    hint: "Property Insights and the Intelligence Worker both contribute to the same record.",
    patch: { focus: null, edge: null, event: null, activity: "all", replay: false },
  },
  {
    n: 3,
    title: "Property Insights",
    hint: "Reads each advised investor’s portfolio and writes that investor a grounded insight card.",
    patch: { focus: "property-insights", edge: null, event: null, activity: "all", replay: false },
  },
  {
    n: 4,
    title: "What it can read",
    hint: "Client holdings the advised investor already owns — not Joseph Mews stock.",
    patch: { focus: "property-insights", edge: "property-properties", event: null, activity: "all", replay: false },
  },
  {
    n: 5,
    title: "Hard walls",
    hint: "It cannot contact investors, advise a buy or sell, or pay a vendor.",
    patch: { focus: "property-insights", edge: null, event: "ev-pay-block", activity: "blocked", replay: false },
  },
  {
    n: 6,
    title: "Intelligence Worker",
    hint: "Clusters investor attention and answers from attached knowledge.",
    patch: { focus: "intent-intelligence", edge: null, event: null, activity: "all", replay: false },
  },
  {
    n: 7,
    title: "Intent signals",
    hint: "Repeat views become a cluster — not an email.",
    patch: { focus: "intent-intelligence", edge: "intent-investor", event: null, activity: "all", replay: false },
  },
  {
    n: 8,
    title: "Needs a person",
    hint: "Lombe House repeat views are waiting for review. No outreach was sent.",
    patch: { focus: "intent-intelligence", edge: "intent-record", event: "ev-intent", activity: "approval", replay: false },
  },
  {
    n: 9,
    title: "Record growth",
    hint: "Accepted notes and clusters accumulate on the company record.",
    patch: { focus: "record", edge: null, event: null, activity: "all", replay: false },
  },
  {
    n: 10,
    title: "Replay",
    hint: "Watch labelled sample outcomes land on the record.",
    patch: { focus: null, edge: null, event: "ev-risk", activity: "all", replay: true },
  },
  {
    n: 11,
    title: "The control room",
    hint: "Both workers, the record, and live activity — this is the intelligence room.",
    patch: { focus: null, edge: null, event: null, activity: "all", replay: false },
  },
];

export function PresentationMode({
  open,
  step,
  onGo,
}: {
  open: boolean;
  step: number;
  onGo: (patch: PresentationPatch) => void;
}) {
  const current = PRESENTATION_STEPS.find((item) => item.n === step) ?? PRESENTATION_STEPS[0];
  const prev = PRESENTATION_STEPS.find((item) => item.n === current.n - 1);
  const next = PRESENTATION_STEPS.find((item) => item.n === current.n + 1);

  if (!open) {
    return (
      <div className="flex items-center justify-end px-3 pt-3 sm:px-4">
        <button
          type="button"
          onClick={() => onGo({ ...PRESENTATION_STEPS[0].patch, present: true, step: 1 })}
          className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-[13px] text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
        >
          <Presentation className="size-4" /> Present
        </button>
      </div>
    );
  }

  return (
    <nav aria-label="Presentation" className="mx-3 mt-3 rounded-2xl border border-border bg-muted/40 px-4 py-3 sm:mx-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Presentation · {current.n} of {PRESENTATION_STEPS.length}
          </p>
          <p className="mt-1 text-sm text-foreground">{current.title}</p>
          <p className="mt-1 text-[12px] text-slate-400">{current.hint}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!prev}
            onClick={() => prev && onGo({ ...prev.patch, present: true, step: prev.n })}
          >
            <ChevronLeft className="size-4" /> Previous
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!next}
            onClick={() => next && onGo({ ...next.patch, present: true, step: next.n })}
          >
            Next <ChevronRight className="size-4" />
          </Button>
          <button
            type="button"
            onClick={() => onGo({ present: false, step: null, replay: false })}
            className={cn("inline-flex min-h-11 items-center px-3 text-[13px] text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300")}
          >
            Exit
          </button>
        </div>
      </div>
    </nav>
  );
}
