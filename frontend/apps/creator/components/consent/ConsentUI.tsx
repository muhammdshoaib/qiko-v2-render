"use client";

import { useEffect, useState } from "react";
import { Settings2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { useConsent } from "./ConsentProvider";

const CHOICE_BUTTON =
  "min-h-11 flex-1 border border-cyan-400/50 bg-slate-900 px-4 text-white hover:bg-slate-800 focus-visible:ring-cyan-300";

export function ConsentBanner() {
  const { acceptAll, rejectNonEssential, openPreferences, consent } = useConsent();

  return (
    <section
      aria-label="Cookie consent"
      className="fixed inset-x-3 bottom-3 z-[100] mx-auto max-w-5xl rounded-2xl border border-slate-700 bg-[#0b101b]/[0.98] p-5 text-slate-200 shadow-2xl shadow-black/60 backdrop-blur sm:inset-x-6 sm:p-6"
    >
      <div className="flex items-start gap-3">
        <ShieldCheck aria-hidden className="mt-0.5 size-6 shrink-0 text-cyan-400" />
        <div>
          <h2 className="text-base font-semibold text-white">Your privacy choices</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-300">
            Qiko uses necessary technologies to operate and secure the service. Analytics and marketing
            technologies are off unless you choose them. None are currently loaded.
          </p>
          {consent.signals.gpc ? (
            <p className="mt-2 text-xs text-cyan-300">Global Privacy Control is active, so marketing remains off.</p>
          ) : consent.signals.dnt ? (
            <p className="mt-2 text-xs text-cyan-300">Do Not Track was detected, so non-essential choices default to off.</p>
          ) : null}
        </div>
      </div>
      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        <Button type="button" onClick={acceptAll} className={CHOICE_BUTTON}>Accept all</Button>
        <Button type="button" onClick={rejectNonEssential} className={CHOICE_BUTTON}>Reject non-essential</Button>
        <Button type="button" onClick={openPreferences} className={CHOICE_BUTTON}>Manage preferences</Button>
      </div>
      <p className="mt-3 text-xs text-slate-400">
        Read our <a href="/cookies" className="text-cyan-300 underline-offset-2 hover:underline">Cookie Policy</a>.
      </p>
    </section>
  );
}

export function ConsentPreferencesDialog() {
  const {
    consent,
    preferencesOpen,
    closePreferences,
    rejectNonEssential,
    savePreferences,
  } = useConsent();
  const [preferences, setPreferences] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const [marketing, setMarketing] = useState(false);

  useEffect(() => {
    if (!preferencesOpen) return;
    setPreferences(consent.preferences);
    setAnalytics(consent.analytics);
    setMarketing(consent.signals.gpc ? false : consent.marketing);
  }, [consent, preferencesOpen]);

  return (
    <Dialog open={preferencesOpen} onOpenChange={(open) => { if (!open) closePreferences(); }}>
      <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto border-slate-700 bg-[#0b101b] text-white sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Cookie preferences</DialogTitle>
          <DialogDescription className="leading-6 text-slate-300">
            Choose whether Qiko may use optional technologies. You can return here at any time.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <PreferenceRow
            id="consent-necessary"
            title="Necessary"
            description="Required for authentication, security, consent records and password reset continuity."
            checked
            disabled
          />
          <PreferenceRow id="consent-preferences" title="Preferences" description="Remembers optional interface settings across visits." checked={preferences} onCheckedChange={setPreferences} />
          <PreferenceRow
            id="consent-analytics"
            title="Analytics"
            description="Would help measure service use. Qiko does not currently load analytics technologies."
            checked={analytics}
            onCheckedChange={setAnalytics}
          />
          <PreferenceRow
            id="consent-marketing"
            title="Marketing"
            description={consent.signals.gpc
              ? "Locked off because your browser sends Global Privacy Control."
              : "Would support marketing measurement. Qiko does not currently load marketing technologies."}
            checked={consent.signals.gpc ? false : marketing}
            disabled={consent.signals.gpc}
            onCheckedChange={setMarketing}
          />
        </div>

        {consent.signals.dnt ? (
          <p className="text-xs leading-5 text-slate-400">
            Your browser sends Do Not Track. Optional technologies started off, but you may change that preference.
          </p>
        ) : null}

        <DialogFooter className="sm:justify-stretch">
          <Button type="button" onClick={rejectNonEssential} className={CHOICE_BUTTON}>
            Reject non-essential
          </Button>
          <Button
            type="button"
            onClick={() => savePreferences({ preferences, analytics, marketing })}
            className={CHOICE_BUTTON}
          >
            Save preferences
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PreferenceRow({
  id,
  title,
  description,
  checked,
  disabled,
  onCheckedChange,
}: {
  id: string;
  title: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-5 rounded-xl border border-slate-700/80 bg-slate-900/70 p-4">
      <label htmlFor={id} className="cursor-pointer">
        <span className="block text-sm font-semibold text-white">{title}</span>
        <span className="mt-1 block text-xs leading-5 text-slate-400">{description}</span>
      </label>
      <Switch
        id={id}
        aria-label={`${title} consent`}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        className="mt-1 data-[state=checked]:bg-cyan-500"
      />
    </div>
  );
}

export function ConsentSettingsButton({ variant = "inline", className = "" }: {
  variant?: "inline" | "floating";
  className?: string;
}) {
  const { openPreferences } = useConsent();

  if (variant === "floating") {
    return (
      <button
        type="button"
        onClick={openPreferences}
        className="fixed bottom-4 right-4 z-[90] inline-flex min-h-11 items-center gap-2 rounded-full border border-slate-600 bg-[#0b101b] px-3 text-xs font-medium text-slate-200 shadow-lg transition-colors hover:border-cyan-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 sm:px-4"
        aria-label="Open cookie settings"
      >
        <Settings2 aria-hidden className="size-4" />
        <span className="hidden sm:inline">Cookie settings</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={openPreferences}
      className={`text-inherit transition-colors hover:text-white focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${className}`}
    >
      Cookie settings
    </button>
  );
}
