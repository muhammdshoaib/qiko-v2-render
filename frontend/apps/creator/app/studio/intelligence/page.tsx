"use client";

import { Suspense, useCallback, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { IntelligenceCockpitShell } from "@/components/intelligence-layer/cockpit-shell";
import { PulseApp } from "@/components/pulse/pulse-app";
import { mergeNav, parsePulseNav, writePulseQuery, type PulseNav } from "@/components/pulse/route";
import { isFocus } from "@/components/pulse/focus";
import {
  ConnectionsTab,
  ObservabilityTab,
  SettingsTab,
  SourcesTab,
  TrainTab,
} from "@/components/intelligence-layer/support-tabs";
import type { CockpitTab, FocusId } from "@/components/intelligence-layer/model";
import { mergeActivity } from "@/components/intelligence-layer/feed";
import { ChannelSurfaces } from "@/components/intelligence-layer/channel-surfaces";
import { useBrain } from "@/lib/brain/store";
import { SHOWCASE_WORKERS } from "@/lib/studio/showcase";

const TABS: CockpitTab[] = ["intelligence", "observability", "train", "sources", "connections", "channels", "settings"];

function isTab(value: string | null): value is CockpitTab {
  return !!value && TABS.includes(value as CockpitTab);
}

export default function IntelligenceLayerPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center bg-[#05070d] text-sm text-slate-400">Loading intelligence…</div>}>
      <IntelligenceLayerScreen />
    </Suspense>
  );
}

function IntelligenceLayerScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const brain = useBrain();
  const feed = useMemo(() => mergeActivity(brain.events), [brain.events]);
  const tab: CockpitTab = isTab(params.get("tab")) ? params.get("tab") as CockpitTab : "intelligence";
  const nav = parsePulseNav(params);
  const focusParam = params.get("focus");
  const focus: FocusId | null = !focusParam || focusParam === "none" ? null : isFocus(focusParam) ? focusParam : null;

  const onPulseNav = useCallback((next: Partial<PulseNav>) => {
    const query = writePulseQuery(mergeNav(nav, next), params, ["demo", "step"]);
    const suffix = query.toString();
    router.replace(suffix ? `/studio/intelligence?${suffix}` : "/studio/intelligence", { scroll: false });
  }, [nav, params, router]);

  const replace = useCallback((next: { tab?: CockpitTab; focus?: FocusId | null; surface?: "claude" | "slack"; channel?: "ops" | "leadership" }) => {
    const query = new URLSearchParams();
    const nextTab = next.tab ?? tab;
    const nextFocus = next.focus === undefined ? focus : next.focus;
    if (nextTab !== "intelligence") query.set("tab", nextTab);
    if (nextFocus) query.set("focus", nextFocus);
    if (nextTab === "channels") {
      query.set("surface", next.surface ?? params.get("surface") ?? "claude");
      const channel = next.channel ?? params.get("channel");
      if (channel) query.set("channel", channel);
    }
    if (params.get("demo") === "1") {
      query.set("demo", "1");
      const step = params.get("step");
      if (step) query.set("step", step);
    }
    const suffix = query.toString();
    router.replace(suffix ? `/studio/intelligence?${suffix}` : "/studio/intelligence", { scroll: false });
  }, [focus, params, router, tab]);

  return (
    <IntelligenceCockpitShell tab={tab} onTabChange={(next) => replace({ tab: next })}>
      {tab === "intelligence" && (
        <div className="h-full overflow-y-auto">
          <PulseApp embedded workers={SHOWCASE_WORKERS} nav={nav} onNav={onPulseNav} />
        </div>
      )}
      {tab === "observability" && (
        <div className="h-full overflow-y-auto p-4 lg:p-6">
          <ObservabilityTab events={feed} onInspect={(next) => replace({ tab: "intelligence", focus: next })} />
        </div>
      )}
      {tab === "train" && (
        <div className="h-full overflow-y-auto p-4 lg:p-6"><TrainTab /></div>
      )}
      {tab === "sources" && (
        <div className="h-full overflow-y-auto p-4 lg:p-6"><SourcesTab /></div>
      )}
      {tab === "connections" && (
        <div className="h-full overflow-y-auto p-4 lg:p-6">
          <ConnectionsTab
            onViewBoundary={(next) => replace({ tab: "intelligence", focus: next })}
            onOpenChannels={(surface) => replace({ tab: "channels", surface })}
          />
        </div>
      )}
      {tab === "channels" && (
        <div className="h-full overflow-y-auto p-4 lg:p-6">
          <ChannelSurfaces />
        </div>
      )}
      {tab === "settings" && (
        <div className="h-full overflow-y-auto p-4 lg:p-6"><SettingsTab /></div>
      )}
    </IntelligenceCockpitShell>
  );
}
