"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

const STORAGE_KEY = "qiko-pulse-referral-v1";

export type ReferralStatus = "proposed" | "exploring" | "deferred" | "approved" | "rejected";
export type ClaudeStep = 0 | 1 | 2 | 3 | 4;

type ReferralState = {
  status: ReferralStatus;
  step: ClaudeStep;
  rate: number;
  decidedAt: string | null;
};

const SEED: ReferralState = { status: "proposed", step: 0, rate: 60, decidedAt: null };

type ReferralApi = ReferralState & {
  ready: boolean;
  explore: () => void;
  setStep: (step: ClaudeStep) => void;
  approve: () => string;
  reject: () => string;
  defer: () => string;
  setRate: (rate: number) => void;
  reset: () => void;
};

const ReferralContext = createContext<ReferralApi | null>(null);

function load(): ReferralState {
  if (typeof window === "undefined") return SEED;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return SEED;
    const parsed = JSON.parse(raw) as Partial<ReferralState>;
    const status = parsed.status === "approved" || parsed.status === "rejected" || parsed.status === "exploring" || parsed.status === "deferred"
      ? parsed.status
      : "proposed";
    const step = [0, 1, 2, 3, 4].includes(Number(parsed.step)) ? Number(parsed.step) as ClaudeStep : 0;
    const rate = typeof parsed.rate === "number" && parsed.rate >= 30 && parsed.rate <= 150 ? parsed.rate : 60;
    return { status, step, rate, decidedAt: parsed.decidedAt ?? null };
  } catch {
    return SEED;
  }
}

function persist(next: ReferralState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

function stamp() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function ReferralProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ReferralState>(SEED);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setState(load());
    setReady(true);
  }, []);

  const api = useMemo<ReferralApi>(() => {
    const commit = (updater: (prev: ReferralState) => ReferralState) => {
      setState((prev) => persist(updater(prev)));
    };
    return {
      ...state,
      ready,
      explore: () => {
        commit((prev) => prev.status === "proposed" ? { ...prev, status: "exploring", step: 0 } : prev);
      },
      setStep: (step) => {
        commit((prev) => ({ ...prev, step, status: prev.status === "proposed" ? "exploring" : prev.status }));
      },
      approve: () => {
        if (state.status === "approved") return "This recommendation is already on the company record.";
        if (state.status === "rejected") return "This recommendation was declined. Reset the demo to try again.";
        commit((prev) => ({ ...prev, status: "approved", decidedAt: stamp(), step: 4 }));
        return "Recommendation written to company intelligence. No investor was contacted.";
      },
      reject: () => {
        if (state.status === "rejected") return "This recommendation was already declined.";
        if (state.status === "approved") return "This recommendation is already on the record.";
        commit((prev) => ({ ...prev, status: "rejected", decidedAt: stamp(), step: 4 }));
        return "Declined. The insight stays. The action was not written.";
      },
      defer: () => {
        if (state.status === "approved") return "This recommendation is already on the company record.";
        if (state.status === "rejected") return "This recommendation was declined. Reset the demo to try again.";
        commit((prev) => ({ ...prev, status: "deferred", decidedAt: null }));
        return "Deferred. The recommendation stays open. Nothing was written.";
      },
      setRate: (rate) => {
        commit((prev) => ({ ...prev, rate }));
      },
      reset: () => {
        commit(() => SEED);
      },
    };
  }, [ready, state]);

  return <ReferralContext.Provider value={api}>{children}</ReferralContext.Provider>;
}

export function useReferral() {
  const value = useContext(ReferralContext);
  if (!value) throw new Error("useReferral must be used inside ReferralProvider");
  return value;
}
