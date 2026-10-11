"use client";

import { Suspense, useCallback, useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { IntelligenceCockpitShell } from "@/components/intelligence-layer/cockpit-shell";
import { LeftPanel } from "@/components/intelligence-layer/left-panel";
import { NetworkCanvas } from "@/components/intelligence-layer/network-canvas";
import { RightRail } from "@/components/intelligence-layer/right-rail";
import {
  ConnectionsTab,
  ObservabilityTab,
  SettingsTab,
  SourcesTab,
  TrainTab,
} from "@/components/intelligence-layer/support-tabs";
import {
  type ActivityFilter,
  type ActivityItem,
  type CockpitTab,
  type FocusId,
} from "@/components/intelligence-layer/model";
import { capturedDecisionCount, mergeActivity } from "@/components/intelligence-layer/feed";
import { WorkflowBoardProvider, useWorkflowBoard } from "@/components/intelligence-layer/workflow-board";
import { useCrm } from "@/lib/crm/store";

const TABS: CockpitTab[] = ["intelligence", "observability", "train", "sources", "connections", "settings"];
const FILTERS: ActivityFilter[] = ["all", "allowed", "blocked", "approval", "completed"];
const FOCUSES: FocusId[] = ["crm-agent", "crm", "claude", "slack-sales", "slack-revenue", "email", "record"];
function isTab(value: string | null): value is CockpitTab {
  return !!value && TABS.includes(value as CockpitTab);
}
function isFocus(value: string | null): value is FocusId {
  return !!value && FOCUSES.includes(value as FocusId);
}
function isFilter(value: string | null): value is ActivityFilter {
  return !!value && FILTERS.includes(value as ActivityFilter);
}

export default function IntelligenceLayerPage() {
  return (
    <Suspense fallback={<div className="flex h-[100dvh] items-center justify-center bg-[#05070d] text-sm text-slate-400">Loading control room…</div>}>
      <WorkflowBoardProvider>
        <IntelligenceLayerScreen />
      </WorkflowBoardProvider>
    </Suspense>
  );
}

function IntelligenceLayerScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const crm = useCrm();
  const board = useWorkflowBoard();
  const feed = useMemo(() => mergeActivity(crm.workflowEvents), [crm.workflowEvents]);
  const tab: CockpitTab = isTab(params.get("tab")) ? params.get("tab") as CockpitTab : "intelligence";
  const focusParam = params.get("focus");
  const focus: FocusId | null = focusParam === "none" ? null : isFocus(focusParam) ? focusParam : "crm-agent";
  const edgeParam = params.get("edge");
  const edgeId = edgeParam && board.edges.some((edge) => edge.id === edgeParam) ? edgeParam : null;
  const activityFilter: ActivityFilter = isFilter(params.get("activity")) ? params.get("activity") as ActivityFilter : "all";
  const eventId = feed.some((item) => item.id === params.get("event")) ? params.get("event") : null;
  const playing = params.get("replay") === "1";

  const replace = useCallback((next: {
    tab?: CockpitTab;
    focus?: FocusId | null;
    edge?: string | null;
    activity?: ActivityFilter;
    event?: string | null;
    replay?: boolean;
  }) => {
    const query = new URLSearchParams();
    const nextTab = next.tab ?? tab;
    const nextFocus = next.focus === undefined ? focus : next.focus;
    const nextEdge = next.edge === undefined ? edgeId : next.edge;
    const nextActivity = next.activity ?? activityFilter;
    const nextEvent = next.event === undefined ? eventId : next.event;
    const nextReplay = next.replay === undefined ? playing : next.replay;
    if (nextTab !== "intelligence") query.set("tab", nextTab);
    if (nextFocus && nextFocus !== "crm-agent") query.set("focus", nextFocus);
    if (nextFocus === null) query.set("focus", "none");
    if (nextEdge) query.set("edge", nextEdge);
    if (nextActivity !== "all") query.set("activity", nextActivity);
    if (nextEvent) query.set("event", nextEvent);
    if (nextReplay) query.set("replay", "1");
    const suffix = query.toString();
    router.replace(suffix ? `/studio/intelligence?${suffix}` : "/studio/intelligence", { scroll: false });
  }, [activityFilter, edgeId, eventId, focus, playing, router, tab]);

  const eventIndex = useMemo(
    () => Math.max(0, feed.findIndex((item) => item.id === eventId)),
    [eventId, feed],
  );

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      const next = feed[eventIndex + 1];
      if (!next) {
        replace({ replay: false });
        return;
      }
      replace({
        event: next.id,
        focus: next.focus === "crm" || next.focus === "claude" || next.focus === "email" || next.focus === "slack-sales" || next.focus === "slack-revenue" ? next.focus : "crm-agent",
        edge: next.edgeId,
        replay: true,
      });
    }, 1600);
    return () => window.clearInterval(timer);
  }, [eventIndex, feed, playing, replace]);

  const selectEvent = (event: ActivityItem) => {
    replace({
      event: event.id,
      focus: event.focus,
      edge: event.edgeId,
      replay: false,
    });
  };

  const step = (direction: -1 | 1) => {
    const next = feed[eventIndex + direction] ?? feed[direction > 0 ? 0 : feed.length - 1];
    selectEvent(next);
  };

  const play = () => {
    const start = eventId && eventIndex < feed.length - 1 ? feed[eventIndex] : feed[0];
    replace({
      event: start.id,
      focus: start.focus,
      edge: start.edgeId,
      activity: "all",
      replay: true,
    });
  };

  if (!crm.ready) {
    return (
      <div className="flex h-[100dvh] items-center justify-center bg-[#05070d] text-sm text-slate-400">
        Loading recorded events…
      </div>
    );
  }

  return (
    <IntelligenceCockpitShell tab={tab} onTabChange={(next) => replace({ tab: next })}>
      {tab === "intelligence" && (
        <div className="grid h-full min-h-0 grid-cols-1 gap-3 overflow-y-auto p-3 lg:grid-cols-[300px_minmax(0,1fr)_320px] lg:overflow-hidden lg:p-4">
          <div className="min-h-0 lg:overflow-hidden">
            <LeftPanel
              focus={focus}
              capturedCount={capturedDecisionCount(crm.workflowEvents)}
              onSelectWorker={() => replace({ focus: "crm-agent", edge: null, event: null })}
              onSelectEvidence={(id) => replace({ edge: id, focus: focus ?? "crm-agent" })}
              onShowAll={() => replace({ focus: null, edge: null, event: null, replay: false })}
            />
          </div>
          <NetworkCanvas
            focus={focus}
            edgeId={edgeId}
            capturedCount={capturedDecisionCount(crm.workflowEvents)}
            pulseEdge={playing ? edgeId : null}
            onFocus={(id) => replace({ focus: id, event: null, edge: null })}
            onSelectEdge={(id) => {
              const edge = board.edgeById(id);
              replace({ edge: id, focus: edge?.to === "record" ? "record" : edge?.to ?? "crm-agent", event: null });
            }}
            onClear={() => replace({ focus: null, edge: null, event: null, replay: false })}
          />
          <div className="min-h-0 lg:overflow-hidden">
            <RightRail
              items={feed}
              capturedCount={capturedDecisionCount(crm.workflowEvents)}
              edgeId={edgeId}
              activityFilter={activityFilter}
              selectedEventId={eventId}
              playing={playing}
              onFilter={(filter) => replace({ activity: filter })}
              onSelectEvent={selectEvent}
              onPlay={play}
              onPause={() => replace({ replay: false })}
              onStep={step}
            />
          </div>
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
          <ConnectionsTab onViewBoundary={(next) => replace({ tab: "intelligence", focus: next })} />
        </div>
      )}
      {tab === "settings" && (
        <div className="h-full overflow-y-auto p-4 lg:p-6"><SettingsTab /></div>
      )}
    </IntelligenceCockpitShell>
  );
}
