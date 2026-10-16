"use client";

import { ArrowRight } from "lucide-react";
import { useReferral } from "@/lib/brain/referral-store";
import { GhostButton, PulseChip } from "./pulse-chrome";
import { REFERRAL, isDecided, statusLabel, statusTone } from "./referral";
import type { PulseNav } from "./route";

export function JourneyCard({ onNav }: { onNav: (next: Partial<PulseNav>) => void }) {
  const referral = useReferral();
  const decided = isDecided(referral.status);

  return (
    <section className="flex flex-col gap-2 rounded-xl border border-primary/20 bg-card px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <p className="text-[14px] font-semibold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
          {REFERRAL.title}
        </p>
        <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {decided ? (
          <>
            <GhostButton onClick={() => onNav({ focus: "record", block: null, worker: null, detail: null, sheet: null })}>
              Company record
              <ArrowRight className="ml-1.5 size-3.5" />
            </GhostButton>
            <GhostButton onClick={() => onNav({ block: "investors", pane: "outcomes", detail: REFERRAL.id })}>
              Open insight
            </GhostButton>
          </>
        ) : (
          <>
            <GhostButton onClick={() => onNav({ block: "investors", pane: "overview", worker: null, detail: null })}>
              Open Investors
              <ArrowRight className="ml-1.5 size-3.5" />
            </GhostButton>
            <GhostButton
              onClick={() =>
                onNav({
                  block: "investors",
                  worker: "intent-intelligence",
                  pane: "outcomes",
                  detail: REFERRAL.id,
                  sheet: null,
                })
              }
            >
              View evidence
            </GhostButton>
          </>
        )}
      </div>
    </section>
  );
}
