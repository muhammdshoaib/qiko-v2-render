"use client";

import { ArrowRight } from "lucide-react";
import { useReferral } from "@/lib/brain/referral-store";
import { GhostButton, PulseChip } from "./pulse-chrome";
import { REFERRAL, statusLabel, statusTone } from "./referral";
import type { PulseNav } from "./route";

export function JourneyCard({ onNav }: { onNav: (next: Partial<PulseNav>) => void }) {
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-primary/25 bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">
            {decided ? "Written to Investors" : "Next move · Investors"}
          </p>
          <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
        </div>
        <h2 className="mt-1 text-[15px] font-semibold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
          {REFERRAL.title}
        </h2>
        <p className="mt-0.5 max-w-[62ch] text-[13px] leading-relaxed text-slate-400">{REFERRAL.insight}</p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {decided ? (
          <>
            <GhostButton onClick={() => onNav({ focus: "record", block: null, worker: null, detail: null, sheet: null })}>
              View company record
              <ArrowRight className="ml-1.5 size-3.5" />
            </GhostButton>
            <GhostButton onClick={() => onNav({ block: "investors", pane: "outcomes", detail: REFERRAL.id })}>
              Open outcome
            </GhostButton>
          </>
        ) : (
          <>
            <GhostButton onClick={() => onNav({ block: "investors", pane: "overview", worker: null, detail: null })}>
              Open Investors
              <ArrowRight className="ml-1.5 size-3.5" />
            </GhostButton>
            <GhostButton
              onClick={() => {
                referral.explore();
                onNav({
                  block: "investors",
                  worker: "intent-intelligence",
                  pane: "outcomes",
                  detail: REFERRAL.id,
                  sheet: "claude",
                });
              }}
            >
              Explore in Claude
            </GhostButton>
          </>
        )}
      </div>
    </section>
  );
}
