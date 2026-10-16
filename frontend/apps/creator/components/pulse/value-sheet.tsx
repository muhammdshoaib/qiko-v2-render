"use client";

import { useReferral } from "@/lib/brain/referral-store";
import { GhostButton, IllustrativeMark } from "./pulse-chrome";
import { REFERRAL, referralHours, referralValue } from "./referral";

export function ValueSheet({ onClose }: { onClose: () => void }) {
  const referral = useReferral();
  const hours = referralHours();
  const value = referralValue(referral.rate);

  return (
    <div className="space-y-4">
      <header>
        <p className="font-mono text-[10.5px] tracking-[0.1em] text-primary uppercase">Knowledge value · illustrative</p>
        <h3 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
          Time saved × an agreed hourly rate
        </h3>
        <p className="mt-1 text-[12.5px] leading-relaxed text-slate-400">
          Illustrative assumption. This is not a measured result from live operations.
        </p>
      </header>

      <dl className="grid gap-3 sm:grid-cols-3">
        <Stat label="Uses (assumption)" value={String(REFERRAL.uses)} hint={REFERRAL.usesLabel} />
        <Stat label="Minutes (assumption)" value={String(REFERRAL.minutes)} hint={REFERRAL.minutesLabel} />
        <Stat label="Hourly rate (you set)" value={`£${referral.rate}`} hint="Agreed rate for this demo" />
      </dl>

      <label className="block">
        <span className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">Adjust the hourly rate</span>
        <input
          type="range"
          min={30}
          max={150}
          step={5}
          value={referral.rate}
          onChange={(event) => referral.setRate(Number(event.target.value))}
          className="mt-2 w-full accent-[#6366F1]"
        />
      </label>

      <aside className="rounded-2xl border border-border bg-muted p-4">
        <p className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">Calculation</p>
        <p className="mt-2 text-[14px] leading-relaxed text-foreground">
          {REFERRAL.uses} × {REFERRAL.minutes} ÷ 60 × £{referral.rate} = {hours.toFixed(2)} hours × £{referral.rate} ≈ <strong>£{value}</strong>
        </p>
        <p className="mt-2 text-[12.5px] text-amber-300/80">
          Uses and minutes are illustrative assumptions. Only the hourly rate is yours to change. No conversion or revenue figure is claimed.
        </p>
      </aside>

      <p className="flex items-center gap-2 text-[12px] text-slate-500">
        <IllustrativeMark />
        Recorded time saved would replace these assumptions in production.
      </p>
      <GhostButton onClick={onClose}>Back to the outcome</GhostButton>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card px-4 py-3">
      <dt className="font-mono text-[10.5px] tracking-[0.08em] text-slate-500 uppercase">{label}</dt>
      <dd className="mt-1 text-[22px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
        {value}
      </dd>
      <dd className="mt-1 text-[12px] text-slate-400">{hint}</dd>
    </div>
  );
}
