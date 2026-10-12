"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { isWorkerId, type FocusId, type WorkerId } from "@/components/intelligence-layer/model";
import { useReferral } from "@/lib/brain/referral-store";
import { useBrain } from "@/lib/brain/store";
import type { ShowcaseWorker } from "@/lib/studio/showcase";
import { AgentView } from "./agent-view";
import { BlockView } from "./block-view";
import { PulseOverview } from "./pulse-overview";
import { blockFromFocus, mergeNav, type PulseNav } from "./route";

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
  const brain = useBrain();
  const referral = useReferral();

  useEffect(() => {
    setOpen(nav);
  }, [nav]);

  const go = (next: Partial<PulseNav>) => {
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

  const openFromMap = (id: FocusId | null) => {
    if (!id) {
      go({ focus: null, block: null, worker: null, detail: null });
      return;
    }
    if (id === "investor-app" || id === "properties") {
      go({ block: id === "investor-app" ? "investors" : "properties", worker: null, focus: null, detail: null });
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

  if (open.worker) {
    return (
      <AgentView
        nav={open}
        workerNames={workerNames}
        onNav={go}
        onApprove={approve}
        onHold={hold}
        onApproveReferral={approveReferral}
        onRejectReferral={rejectReferral}
      />
    );
  }

  if (open.block) {
    return (
      <BlockView
        nav={open}
        workerNames={workerNames}
        onNav={go}
        onApprove={approve}
        onHold={hold}
        onApproveReferral={approveReferral}
        onRejectReferral={rejectReferral}
      />
    );
  }

  return (
    <PulseOverview
      workers={workers}
      focus={open.focus}
      onFocus={openFromMap}
      onHighlight={highlightOnMap}
      onNav={go}
      embedded={embedded}
    />
  );
}
