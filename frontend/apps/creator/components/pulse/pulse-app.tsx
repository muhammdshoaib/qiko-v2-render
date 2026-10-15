"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { isWorkerId, type FocusId, type WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { useBrain } from "@/lib/brain/store";
import type { ShowcaseWorker } from "@/lib/studio/showcase";
import { AgentView } from "./agent-view";
import { AskBrainChat, AskBrainTrigger, useAskBrainShortcut } from "./ask-brain";
import { BlockView } from "./block-view";
import { PulseOverview } from "./pulse-overview";
import { blockFromFocus, knowledgeBlockHref, mergeNav, type PulseNav } from "./route";

export function PulseApp({
  workers,
  nav,
  onNav,
  embedded = false,
}: {
  workers: ShowcaseWorker[];
  nav: PulseNav;
  onNav: (next: Partial<PulseNav>) => void;
  embedded?: boolean;
}) {
  const [open, setOpen] = useState(nav);
  const [brainOpen, setBrainOpen] = useState(false);
  const brain = useBrain();
  const referral = useReferral();
  const toggleBrain = useCallback(() => setBrainOpen((current) => !current), []);
  useAskBrainShortcut(toggleBrain);

  useEffect(() => {
    setOpen(nav);
  }, [nav]);

  const go = (next: Partial<PulseNav>) => {
    // Leave Pulse for Knowledge block pages without mounting Agent/Block view first.
    if (knowledgeBlockHref(next)) {
      onNav(next);
      return;
    }
    setOpen((current) => mergeNav(current, next));
    onNav(next);
  };
  const workerNames = Object.fromEntries(workers.map((worker) => [worker.slug, worker.name])) as Partial<Record<WorkerId, string>>;
  const approve = brain.approval === "awaiting"
    ? () => toast.message(brain.approveFollowUp())
    : undefined;
  const hold = brain.approval === "awaiting"
    ? () => toast.message(brain.holdFollowUp())
    : undefined;

  const approveReferral = () => {
    toast.message(referral.approve());
    go({ block: "investors", pane: "outcomes", detail: "o-referral", sheet: null });
  };
  const rejectReferral = () => {
    toast.message(referral.reject());
    go({ block: "investors", pane: "outcomes", detail: "o-referral", sheet: null });
  };
  const deferReferral = () => {
    toast.message(referral.defer());
    go({ block: "investors", pane: "outcomes", detail: "o-referral", sheet: null });
  };

  const openFromMap = (id: FocusId | null) => {
    if (!id) {
      go({ focus: null, block: null, worker: null, detail: null });
      return;
    }
    // Knowledge block circle → that worker's detailed view (1 block = 1 worker).
    if (id === "investor-app") {
      go({ block: "investors", worker: "intent-intelligence", focus: null, detail: null });
      return;
    }
    if (id === "properties") {
      go({ block: "properties", worker: "property-insights", focus: null, detail: null });
      return;
    }
    if (isWorkerId(id)) {
      go({ block: blockFromFocus(id), worker: id, focus: null, detail: null });
      return;
    }
    go({ focus: id, block: null, worker: null, detail: null });
  };

  const highlightOnMap = (id: FocusId | null) => {
    go({ focus: id, block: null, worker: null, detail: null });
  };

  const askBrain = <AskBrainTrigger open={brainOpen} onToggle={toggleBrain} />;

  return (
    <>
      {open.worker ? (
        <>
          <div className="mx-auto flex w-full max-w-[1400px] justify-end px-4 pt-4 sm:px-6 lg:px-8">{askBrain}</div>
          <AgentView
            nav={open}
            workerNames={workerNames}
            onNav={go}
            onApprove={approve}
            onHold={hold}
            onApproveReferral={approveReferral}
            onRejectReferral={rejectReferral}
            onDeferReferral={deferReferral}
          />
        </>
      ) : open.block ? (
        <>
          <div className="mx-auto flex w-full max-w-[1400px] justify-end px-4 pt-4 sm:px-6 lg:px-8">{askBrain}</div>
          <BlockView
            nav={open}
            workerNames={workerNames}
            onNav={go}
            onApprove={approve}
            onHold={hold}
            onApproveReferral={approveReferral}
            onRejectReferral={rejectReferral}
            onDeferReferral={deferReferral}
          />
        </>
      ) : (
        <PulseOverview
          workers={workers}
          focus={open.focus}
          onFocus={openFromMap}
          onHighlight={highlightOnMap}
          onNav={go}
          embedded={embedded}
          askBrain={askBrain}
        />
      )}
      {brainOpen && <AskBrainChat onClose={() => setBrainOpen(false)} onNav={go} />}
    </>
  );
}
