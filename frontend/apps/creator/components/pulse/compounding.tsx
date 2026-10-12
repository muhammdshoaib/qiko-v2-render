"use client";

import { useReferral } from "@/lib/brain/referral-store";
import { PulseChip } from "./pulse-chrome";
import { REFERRAL, statusLabel, statusTone } from "./referral";

export function CompoundingPanel({ compact = false }: { compact?: boolean }) {
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";
  const captured = referral.status === "approved"
    ? REFERRAL.captured.approved
    : referral.status === "rejected"
      ? REFERRAL.captured.rejected
      : [];
  const future = referral.status === "approved"
    ? REFERRAL.futureUse.approved
    : referral.status === "rejected"
      ? REFERRAL.futureUse.rejected
      : "";

  if (compact) {
    return (
      <aside className="rounded-2xl border border-white/10 bg-muted p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">What this captured</p>
          <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
        </div>
        {!decided ? (
          <p className="mt-2 text-[13px] leading-relaxed text-slate-400">
            Approve or decline to capture a decision. The worker does not learn automatically.
          </p>
        ) : (
          <>
            <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[13px] leading-relaxed text-foreground">
              {captured.map((line) => <li key={line}>{line}</li>)}
            </ul>
            <p className="mt-3 text-[12.5px] leading-relaxed text-slate-400">{future}</p>
          </>
        )}
      </aside>
    );
  }

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
            Nothing new is on the record yet. Approve or decline to capture a decision. The worker does not learn automatically.
          </p>
        ) : (
          <>
            <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[13px] leading-relaxed text-foreground">
              {captured.map((line) => <li key={line}>{line}</li>)}
            </ul>
            <p className="mt-3 text-[12.5px] leading-relaxed text-slate-400">{future}</p>
          </>
        )}
      </article>
    </div>
  );
}
