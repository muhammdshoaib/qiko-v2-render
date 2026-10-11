import { ACTIVITY, toActivityItem, type ActivityItem } from "./model";
import type { WorkflowEvent } from "@/lib/crm/types";

export function mergeActivity(workflowEvents: WorkflowEvent[]): ActivityItem[] {
  const live = workflowEvents.map((event) => toActivityItem({
    id: event.id,
    title: event.title,
    detail: event.detail,
    at: event.at,
    filter: event.filter,
    edgeId: event.edgeId,
    focus: event.focus,
  }));
  const liveIds = new Set(live.map((item) => item.id));
  const liveTitles = new Set(live.map((item) => item.title));
  return [
    ...live,
    ...ACTIVITY.filter((item) => !liveIds.has(item.id) && !liveTitles.has(item.title)),
  ];
}

export function capturedDecisionCount(workflowEvents: WorkflowEvent[]) {
  return 47 + workflowEvents.filter((event) => event.edgeId === "agent-record").length;
}
