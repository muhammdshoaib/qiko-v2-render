import { ACTIVITY, CAPTURED_DECISIONS, type ActivityItem } from "./model";

export function mergeActivity(extra: ActivityItem[] = []): ActivityItem[] {
  const seen = new Set(ACTIVITY.map((item) => item.id));
  return [...extra.filter((item) => !seen.has(item.id)), ...ACTIVITY];
}

export function capturedDecisionCount(extraCompleted = 0) {
  return CAPTURED_DECISIONS + extraCompleted;
}
