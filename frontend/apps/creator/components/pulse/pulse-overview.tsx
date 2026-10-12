"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Presentation } from "lucide-react";
import { toast } from "sonner";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import { studioAttention, useBrain } from "@/lib/brain/store";
import { RECENT_ACTIONS, type ShowcaseWorker } from "@/lib/studio/showcase";
import { useReferral } from "@/lib/brain/referral-store";
import { JourneyCard } from "./journey-card";
import { PulseDrawer } from "./pulse-drawer";
import { PulseFeed } from "./pulse-feed";
import { PulseMap } from "./pulse-map";
import { REFERRAL, decisionLabel } from "./referral";
import type { PulseNav } from "./route";

export function PulseOverview({
  workers,
  focus,
  onFocus,
  onNav,
  embedded = false,
}: {
  workers: ShowcaseWorker[];
  focus: FocusId | null;
  onFocus: (id: FocusId | null) => void;
  onNav: (next: Partial<PulseNav>) => void;
  embedded?: boolean;
}) {
  const [open, setOpen] = useState<FocusId | null>(focus);
  const brain = useBrain();
  const referral = useReferral();
  const attention = !brain.ready ? [] : studioAttention(brain.approval).filter((item) => item.status === "attention");
  const completedReview = !brain.ready ? [] : studioAttention(brain.approval).filter((item) => item.status === "completed");
  const workerNames = Object.fromEntries(workers.map((worker) => [worker.slug, worker.name])) as Partial<Record<WorkerId, string>>;
  const decided = referral.status === "approved" || referral.status === "rejected";
  const openReferral = () => onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL.id });
  const journeyLead = {
    title: REFERRAL.title,
    detail: decided ? decisionLabel(referral.status) : REFERRAL.insight,
    at: referral.decidedAt ?? "Today, 10:12",
    originLabel: "Investors · Intelligence Worker",
    status: decided ? "completed" as const : "attention" as const,
    onOpen: openReferral,
  };

  useEffect(() => {
    setOpen(focus);
  }, [focus]);

  const select = (id: FocusId | null) => {
    setOpen(id);
    onFocus(id);
  };

  return (
    <div className="min-h-full bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        {!embedded && (
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-mono text-[11px] tracking-[0.14em] text-violet-400 uppercase">Pulse</p>
            <h1 className="mt-1 text-[26px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
              Company intelligence
            </h1>
            <p className="mt-1 max-w-[54ch] text-[13.5px] text-slate-400">
              Joseph Mews · two knowledge blocks, two workers, and one end-to-end outcome on Investors.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <HonestyBadge kind="illustrative" />
            <Link
              href="/studio?demo=1&step=1"
              className="inline-flex min-h-11 items-center gap-2 text-[13px] text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
            >
              <Presentation className="size-4" /> Present
            </Link>
          </div>
        </header>
        )}

        <JourneyCard onNav={onNav} />
        <PulseMap focus={open} workerNames={workerNames} onSelect={select} />
        <PulseFeed
          attention={attention}
          recent={[...completedReview, ...RECENT_ACTIONS]}
          leadAttention={decided ? null : journeyLead}
          leadRecent={decided ? journeyLead : null}
          onOpen={select}
          onApprove={brain.approval === "awaiting" ? () => toast.message(brain.approveFollowUp()) : undefined}
          onHold={brain.approval === "awaiting" ? () => toast.message(brain.holdFollowUp()) : undefined}
        />
      </div>
      <PulseDrawer focus={open} workerNames={workerNames} onClose={() => select(null)} onSelect={select} />
    </div>
  );
}
