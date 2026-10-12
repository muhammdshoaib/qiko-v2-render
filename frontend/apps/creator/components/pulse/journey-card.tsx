"use client";

import { ArrowRight } from "lucide-react";
import { useReferral } from "@/lib/brain/referral-store";
import { GhostButton, IllustrativeMark, PulseChip } from "./pulse-chrome";
import { REFERRAL, statusLabel, statusTone } from "./referral";
import type { PulseNav } from "./route";

export function JourneyCard({ onNav }: { onNav: (next: Partial<PulseNav>) => void }) {
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";

  return (
    <section className="overflow-hidden rounded-[22px] border border-primary/25 bg-card shadow-[0_18px_40px_-28px_rgba(0,0,0,0.55)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] px-5 py-3">
        <div>
          <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">Next move · Investors</p>
          <h2 className="mt-1 text-[17px] font-semibold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
            {REFERRAL.title}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <IllustrativeMark />
          <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
        </div>
      </div>
      <div className="grid gap-0 lg:grid-cols-[1.4fr_0.9fr]">
        <div className="px-5 py-4">
          <p className="text-[13.5px] leading-relaxed text-foreground">{REFERRAL.insight}</p>
          <p className="mt-2 text-[12.5px] leading-relaxed text-slate-400">{REFERRAL.caution}</p>
          <p className="mt-3 text-[13px] text-foreground">
            <span className="font-medium">Suggested action. </span>
            {REFERRAL.action}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <GhostButton
              onClick={() => {
                referral.explore();
                onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL.id, sheet: "claude" });
              }}
            >
              {decided ? "Review in Claude" : "Explore in Claude"}
              <ArrowRight className="ml-1.5 size-3.5" />
            </GhostButton>
            <GhostButton onClick={() => onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL.id })}>
              Open outcome
            </GhostButton>
            <GhostButton onClick={() => onNav({ block: "investors", worker: null, detail: null })}>Investors block</GhostButton>
          </div>
        </div>
        <aside className="border-t border-white/[0.06] bg-muted px-5 py-4 lg:border-t-0 lg:border-l">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">Why this is recommended</p>
          <ul className="mt-2 space-y-2">
            {REFERRAL.why.map((line) => (
              <li key={line} className="text-[12.5px] leading-relaxed text-slate-400">
                {line}
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </section>
  );
}
