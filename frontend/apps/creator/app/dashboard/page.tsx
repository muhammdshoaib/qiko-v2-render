"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { PulseApp } from "@/components/pulse/pulse-app";
import { mergeNav, type PulseNav } from "@/components/pulse/route";
import { SHOWCASE_WORKERS } from "@/lib/studio/showcase";

const INITIAL: PulseNav = {
  block: null,
  worker: null,
  pane: "overview",
  detail: null,
  focus: null,
  sheet: null,
};

export default function PulseDashboardPage() {
  const router = useRouter();
  const [nav, setNav] = useState<PulseNav>(INITIAL);

  const onNav = useCallback((next: Partial<PulseNav>) => {
    // Sprint brief: Investors opens the knowledge-block screen (same tab bar as today's worker).
    if (next.block === "investors" || next.worker === "intent-intelligence") {
      router.push("/knowledge/investors");
      return;
    }
    setNav((current) => mergeNav(current, next));
  }, [router]);

  return (
    <AppShell title="Pulse">
      <PulseApp workers={SHOWCASE_WORKERS} nav={nav} onNav={onNav} embedded />
    </AppShell>
  );
}
