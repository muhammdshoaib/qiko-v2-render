"use client";

import { useReferral } from "@/lib/brain/referral-store";
import { CompoundingPanel } from "./compounding";
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
  const recorded = referral.status === "approved"
    ? REFERRAL.recordedResult.approved
    : referral.status === "rejected"
      ? REFERRAL.recordedResult.rejected
      : REFERRAL.recordedResult.pending;

  return (
    <article className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <IllustrativeMark />
        <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
      </div>

      <Field label="What was discovered?">{REFERRAL.insight}</Field>

      <Field label="What evidence supports it?">
        {REFERRAL.why.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <p className="mt-2 text-amber-300/80">{REFERRAL.caution}</p>
        {!compact && (
          <button
            type="button"
            onClick={() => onNav({
              block: "investors",
              worker: "intent-intelligence",
              pane: "conversations",
              detail: REFERRAL_EVIDENCE_ID,
              sheet: null,
            })}
            className="mt-2 text-[12.5px] font-medium text-primary hover:underline"
          >
            Open the labelled sample
          </button>
        )}
      </Field>

      <Field label="What does Qiko recommend?">{REFERRAL.action}</Field>

      <Field label={decided ? "What happened after the action?" : "What action can you take?"}>
        <p>{decisionLabel(referral.status)}</p>
        {referral.decidedAt ? <p className="mt-1 text-slate-500">Recorded at {referral.decidedAt}.</p> : null}
        <p className="mt-1 text-slate-500">{destinationLabel(referral.status)}</p>
      </Field>

      {decided && <CompoundingPanel compact />}

      <Field label="How will the result be measured?">{REFERRAL.measurement}</Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <aside className="rounded-2xl border border-white/10 bg-muted p-4">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">Estimated benefit</p>
          <p className="mt-2 text-[13px] leading-relaxed text-foreground">
            {REFERRAL.uses} uses × {REFERRAL.minutes} min × £{referral.rate}/hr ≈ {hours.toFixed(2)} hours · £{value}
          </p>
          <p className="mt-2 text-[12.5px] text-amber-300/80">{REFERRAL.estimatedNote}</p>
          {!compact && (
            <button
              type="button"
              onClick={() => onNav({
                block: "investors",
                worker: "intent-intelligence",
                pane: "outcomes",
                detail: REFERRAL.id,
                sheet: "value",
              })}
              className="mt-2 text-[12.5px] font-medium text-primary hover:underline"
            >
              Show the calculation
            </button>
          )}
        </aside>
        <aside className="rounded-2xl border border-white/10 bg-card p-4">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">Recorded result</p>
          <p className="mt-2 text-[13px] leading-relaxed text-foreground">{recorded}</p>
        </aside>
      </div>

      {!compact && (
        <div className="flex flex-wrap gap-2 pt-1">
          {!decided && (
            <>
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
              {onApprove && onReject && (
                <>
                  <GhostButton onClick={onApprove}>Approve to company record</GhostButton>
                  <GhostButton onClick={onReject}>Decline</GhostButton>
                </>
              )}
            </>
          )}
          {decided && (
            <>
              <GhostButton
                onClick={() => onNav({
                  block: null,
                  worker: null,
                  pane: "overview",
                  detail: null,
                  sheet: null,
                  focus: "record",
                })}
              >
                View company record
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
                Review in Claude
              </GhostButton>
              <GhostButton onClick={() => referral.reset()}>Replay this example</GhostButton>
            </>
          )}
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
