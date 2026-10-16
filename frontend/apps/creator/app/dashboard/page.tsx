"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { PulseApp } from "@/components/pulse/pulse-app";
import { knowledgeBlockHref, mergeNav, type PulseNav } from "@/components/pulse/route";
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
  return (
    <Suspense fallback={<AppShell title="Pulse"><div className="p-6 text-sm text-slate-400">Loading Pulse…</div></AppShell>}>
      <PulseDashboardScreen />
    </Suspense>
  );
}

function PulseDashboardScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const [nav, setNav] = useState<PulseNav>(INITIAL);

  useEffect(() => {
    const view = params.get("view");
    if (view !== "insights" && view !== "outcomes") return;
    const el = document.getElementById("insights") ?? document.getElementById("outcomes");
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [params]);

  const onNav = useCallback((next: Partial<PulseNav>) => {
    const href = knowledgeBlockHref(next);
    if (href) {
      router.push(href);
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
