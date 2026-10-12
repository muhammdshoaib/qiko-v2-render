"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { Presentation } from "lucide-react";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { useBrain } from "@/lib/brain/store";
import { RECENT_ACTIONS, type ShowcaseWorker } from "@/lib/studio/showcase";
import { JourneyCard } from "./journey-card";
import { KnowledgeGrowth } from "./knowledge-growth";
import { PulseDrawer } from "./pulse-drawer";
import { PulseFeed } from "./pulse-feed";
import { PulseMap } from "./pulse-map";
import { companyIntel } from "./record-summary";
import { REFERRAL, decisionLabel, isDecided } from "./referral";
import type { PulseNav } from "./route";

export function PulseOverview({
  workers,
  focus,
  onFocus,
  onHighlight,
  onNav,
  embedded = false,
  askBrain,
}: {
  workers: ShowcaseWorker[];
  focus: FocusId | null;
  onFocus: (id: FocusId | null) => void;
  onHighlight?: (id: FocusId | null) => void;
  onNav: (next: Partial<PulseNav>) => void;
  embedded?: boolean;
  askBrain?: ReactNode;
}) {
  const [open, setOpen] = useState<FocusId | null>(focus);
  const [growthMonth, setGrowthMonth] = useState<string | null>(null);
  const brain = useBrain();
  const referral = useReferral();
  const intel = companyIntel(referral.status, brain.approval);
  const decided = isDecided(referral.status);
  const attention: typeof RECENT_ACTIONS = [];
  const completedReview: typeof RECENT_ACTIONS = [
    {
      title: "Lombe House intent captured",
      detail: "An investor viewed Lombe House repeatedly. The intent worker flagged interest. Labelled sample — not the live admin feed. No outreach was sent.",
      at: "Today, 09:40",
      status: "completed",
      origin: "investor-app",
      originLabel: "Investors · Intelligence Worker",
    },
    ...RECENT_ACTIONS,
  ];
  const referralLead = {
    title: REFERRAL.title,
    at: referral.decidedAt ? `Today, ${referral.decidedAt}` : "Today, 10:12",
    originLabel: decided ? "Company intelligence" : "Investors",
  };
  const workerNames = Object.fromEntries(workers.map((worker) => [worker.slug, worker.name])) as Partial<Record<WorkerId, string>>;
  const highlightOrigin = onHighlight ?? onFocus;

  useEffect(() => {
    setOpen(focus);
  }, [focus]);

  const highlight = (id: FocusId | null) => {
    setOpen(id);
    highlightOrigin(id);
  };

  const openNode = (id: FocusId) => {
    setOpen(id);
    onFocus(id);
  };

  return (
    <div className="min-h-full bg-background text-foreground">
      <div className={`mx-auto flex w-full max-w-[1400px] flex-col gap-4 px-4 sm:px-6 lg:px-8 ${embedded ? "py-4" : "py-6 sm:py-8"}`}>
        {embedded && askBrain && (
          <div className="flex justify-end">{askBrain}</div>
        )}
        {!embedded && (
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-mono text-[11px] tracking-[0.14em] text-violet-400 uppercase">Pulse</p>
            <h1 className="mt-1 text-[26px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
              Company intelligence
            </h1>
            <p className="mt-1 max-w-[54ch] text-[13.5px] text-slate-400">
              What Joseph Mews knows, what it has learned, and how that record is accumulating.
            </p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-3 sm:w-auto">
            {askBrain}
            <HonestyBadge kind="illustrative" />
            <Link
              href="/studio/intelligence?demo=1&step=1"
              className="inline-flex min-h-11 items-center gap-2 text-[13px] text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
            >
              <Presentation className="size-4" /> Present
            </Link>
          </div>
        </header>
        )}

        <JourneyCard onNav={onNav} />
        <PulseMap focus={open} workerNames={workerNames} onSelect={openNode} />
        {open !== "record" && (
        <KnowledgeGrowth
          compact
          points={intel.growth}
          selected={growthMonth ?? intel.growth[intel.growth.length - 1]?.month ?? "Oct"}
          onSelect={setGrowthMonth}
        />
        )}
        <PulseFeed
          attention={attention}
          recent={completedReview}
          leadAttention={!decided ? {
            ...referralLead,
            detail: referral.status === "deferred"
              ? "Deferred — still needs a person. Nothing was written."
              : "1 of 9 labelled reachouts still needs a person. Lombe House intent is the worked example. Nothing will be sent automatically.",
            status: "attention",
            onOpen: () => onNav({ block: "investors", pane: "overview" }),
          } : null}
          leadRecent={decided ? {
            ...referralLead,
            detail: decisionLabel(referral.status),
            status: "completed",
            onOpen: () => highlight("record"),
          } : null}
          onOpen={highlight}
        />
      </div>
      <PulseDrawer
        focus={open}
        workerNames={workerNames}
        growthMonth={growthMonth ?? intel.growth[intel.growth.length - 1]?.month ?? "Oct"}
        onGrowthMonth={setGrowthMonth}
        onClose={() => highlight(null)}
        onSelect={highlight}
        onOpen={openNode}
        onNav={onNav}
      />
    </div>
  );
}
