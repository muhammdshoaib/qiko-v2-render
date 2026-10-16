"use client";

import { useReferral, type ClaudeStep } from "@/lib/brain/referral-store";
import { GhostButton, IllustrativeMark, PulseChip } from "./pulse-chrome";
import { CLAUDE_STEPS, REFERRAL, isDecided, statusLabel, statusTone } from "./referral";

export function ClaudeWalkthrough({
  onApprove,
  onReject,
  onDefer,
  onClose,
  onViewRecord,
}: {
  onApprove?: () => void;
  onReject?: () => void;
  onDefer?: () => void;
  onClose: () => void;
  onViewRecord?: () => void;
}) {
  const referral = useReferral();
  const decided = isDecided(referral.status);
  const visible = CLAUDE_STEPS.filter((item) => item.id <= referral.step);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <IllustrativeMark />
        <PulseChip>Simulated Claude</PulseChip>
        <PulseChip tone={statusTone(referral.status)}>{statusLabel(referral.status)}</PulseChip>
      </div>

      <ol className="flex flex-wrap gap-1.5" aria-label="Walkthrough steps">
        {CLAUDE_STEPS.map((item) => {
          const current = item.id === referral.step;
          return (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => referral.setStep(item.id)}
                className={`min-h-9 rounded-full px-3 text-[11.5px] font-medium ${
                  current ? "bg-white text-foreground" : item.id < referral.step ? "bg-muted text-slate-700" : "bg-transparent text-slate-500 ring-1 ring-white/10"
                }`}
              >
                {item.id + 1}. {item.title}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="space-y-3 rounded-2xl border border-border bg-muted p-4">
        {visible.map((item) => (
          <div key={item.id} className="space-y-2">
            <div className="ml-auto max-w-[92%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2.5 text-[13px] leading-relaxed text-white">
              {item.prompt}
            </div>
            <div className="max-w-[94%] rounded-2xl rounded-bl-md bg-card px-3.5 py-2.5 text-[13px] leading-relaxed text-foreground ring-1 ring-white/10">
              {item.reply}
            </div>
          </div>
        ))}
      </div>

      {referral.step === 3 && (
        <aside className="rounded-2xl border border-border bg-card p-4">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">Defined example output</p>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-[13px] leading-relaxed text-foreground">
            {REFERRAL.expectedOutput.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </aside>
      )}

      {referral.step === 4 && !decided && (
        <aside className="rounded-2xl border border-amber-400/20 bg-amber-400/10 p-4">
          <p className="text-[13.5px] font-medium text-foreground">Confirm the action</p>
          <p className="mt-1 text-[12.5px] text-slate-400">Approving writes the recommendation to the shared Investors record. Declining keeps the insight and writes nothing.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {onApprove && <GhostButton onClick={onApprove}>Approve to company record</GhostButton>}
            {onReject && <GhostButton onClick={onReject}>Decline</GhostButton>}
            {onDefer && <GhostButton onClick={onDefer}>Defer</GhostButton>}
          </div>
        </aside>
      )}

      {decided && (
        <aside className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-[13.5px] font-medium text-foreground">Decision captured in this prototype</p>
          <p className="mt-1 text-[12.5px] text-slate-400">
            {referral.status === "approved"
              ? "The recommendation now sits on the Investors record and in Pulse activity. Nothing was sent to an investor."
              : "The insight remains visible. The action was not written."}
          </p>
          {onViewRecord && (
            <div className="mt-3">
              <GhostButton onClick={onViewRecord}>View company record</GhostButton>
            </div>
          )}
        </aside>
      )}

      <div className="flex flex-wrap gap-2">
        {referral.step < 4 && (
          <GhostButton onClick={() => referral.setStep((referral.step + 1) as ClaudeStep)}>
            Next: {CLAUDE_STEPS[referral.step + 1].title}
          </GhostButton>
        )}
        {referral.step > 0 && (
          <GhostButton onClick={() => referral.setStep((referral.step - 1) as ClaudeStep)}>Previous</GhostButton>
        )}
        <GhostButton onClick={onClose}>Close walkthrough</GhostButton>
      </div>
    </div>
  );
}
