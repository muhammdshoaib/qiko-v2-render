"use client";

import { useReferral } from "@/lib/brain/referral-store";
import { PulseChip } from "./pulse-chrome";
import { statusLabel, statusTone } from "./referral";

export function CompoundingPanel() {
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <article className="rounded-2xl border border-white/10 bg-muted p-4">
        <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">What the company knew</p>
        <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[13px] leading-relaxed text-foreground">
          <li>Repeat investor-app views can cluster on one development (Lombay House).</li>
          <li>Quiet listings can be recorded without contacting anyone.</li>
          <li>No referral pattern sat on the shared Investors record.</li>
        </ul>
      </article>
      <article className="rounded-2xl border border-white/10 bg-card p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">What changed</p>
          <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
        </div>
        {!decided ? (
          <p className="mt-2 text-[13px] leading-relaxed text-slate-400">
            Nothing new is on the record yet. Approve or reject to capture a decision. The worker does not learn automatically.
          </p>
        ) : referral.status === "approved" ? (
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[13px] leading-relaxed text-foreground">
            <li>The labelled sample is now a captured decision: referrals reached review more often than portal-only views.</li>
            <li>The recommended thank-you brief is written to company intelligence.</li>
            <li>A later briefing could reuse this recorded pattern. That reuse is described here — it is not an automatic model update.</li>
          </ul>
        ) : (
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[13px] leading-relaxed text-foreground">
            <li>The insight remains visible as a declined recommendation.</li>
            <li>The action was not written. Later recommendations should not treat a thank-you programme as agreed.</li>
            <li>That is the demonstrated learning: a human decision now sits on the record.</li>
          </ul>
        )}
      </article>
    </div>
  );
}
