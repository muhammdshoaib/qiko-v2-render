"use client";

import { useReferral } from "@/lib/brain/referral-store";
import { GhostButton, IllustrativeMark, PulseChip } from "./pulse-chrome";
import {
  REFERRAL,
  REFERRAL_EVIDENCE_ID,
  decisionLabel,
  destinationLabel,
  referralHours,
  referralValue,
  statusLabel,
  statusTone,
} from "./referral";
import type { PulseNav } from "./route";

export function OutcomeRecord({
  onNav,
  onApprove,
  onReject,
  compact = false,
}: {
  onNav: (next: Partial<PulseNav>) => void;
  onApprove?: () => void;
  onReject?: () => void;
  compact?: boolean;
}) {
  const referral = useReferral();
  const decided = referral.status === "approved" || referral.status === "rejected";
  const hours = referralHours();
  const value = referralValue(referral.rate);

  return (
    <article className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">Outcome record · Investors</p>
          <h3 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
            {REFERRAL.title}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <IllustrativeMark />
          <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
        </div>
      </header>

      <Field label="Original insight">{REFERRAL.insight}</Field>
      <Field label="Supporting evidence">
        {REFERRAL.why.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <p className="mt-2 text-amber-300/80">{REFERRAL.caution}</p>
        <button
          type="button"
          onClick={() => onNav({ block: "investors", worker: "intent-intelligence", pane: "conversations", detail: REFERRAL_EVIDENCE_ID })}
          className="mt-2 text-[12.5px] font-medium text-primary hover:underline"
        >
          Open the labelled sample conversation
        </button>
      </Field>
      <Field label="Recommended action">{REFERRAL.action}</Field>
      <Field label="User decision">
        {decisionLabel(referral.status)}
        {referral.decidedAt ? <span className="mt-1 block text-slate-500">Recorded at {referral.decidedAt}.</span> : null}
      </Field>
      <Field label="Current status">{statusLabel(referral.status)}</Field>
      <Field label="Destination of the output">{destinationLabel(referral.status)}</Field>
      <Field label="Benefit — illustrative assumption, not a measured result">
        <p>
          {REFERRAL.uses} uses × {REFERRAL.minutes} minutes × £{referral.rate}/hr = {hours.toFixed(2)} hours × £{referral.rate} ≈ £{value}.
        </p>
        <p className="mt-1">
          Uses and minutes are labelled assumptions for this prototype. Change the hourly rate on the value sheet.
        </p>
        <button
          type="button"
          onClick={() => onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL.id, sheet: "value" })}
          className="mt-2 text-[12.5px] font-medium text-primary hover:underline"
        >
          Show the calculation
        </button>
      </Field>
      <Field label="Follow-up or measurement plan">{REFERRAL.measurement}</Field>

      {!compact && (
        <div className="flex flex-wrap gap-2 pt-1">
          <GhostButton
            onClick={() => {
              referral.explore();
              onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL.id, sheet: "claude" });
            }}
          >
            {decided ? "Review in Claude" : "Explore in Claude"}
          </GhostButton>
          {!decided && onApprove && onReject && (
            <>
              <GhostButton onClick={onApprove}>Approve to company record</GhostButton>
              <GhostButton onClick={onReject}>Reject</GhostButton>
            </>
          )}
          <GhostButton onClick={() => onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes" })}>
            Intelligence Worker
          </GhostButton>
        </div>
      )}
    </article>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section>
      <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">{label}</p>
      <div className="mt-1 space-y-1 text-[13px] leading-relaxed text-foreground">{children}</div>
    </section>
  );
}
