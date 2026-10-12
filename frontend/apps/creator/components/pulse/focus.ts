import type { FocusId } from "@/components/intelligence-layer/model";

export const FOCUSES: FocusId[] = [
  "property-insights",
  "intent-intelligence",
  "properties",
  "investor-app",
  "knowledge",
  "chat",
  "record",
];

export function isFocus(value: string | null): value is FocusId {
  return !!value && FOCUSES.includes(value as FocusId);
}
