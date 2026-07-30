export const LOSS_REASONS = [
  "price",
  "technical",
  "relationship",
  "timeline",
  "no_bid_decision",
  "other",
] as const;

export type LossReason = (typeof LOSS_REASONS)[number];
export type OutcomeDraft = "pending" | "won" | "lost" | "withdrawn";
export const MAX_OUTCOME_VALUE = 1_000_000_000_000_000;

export type OutcomePayload = {
  outcome: Exclude<OutcomeDraft, "pending"> | null;
  reason: string;
  value: number | null;
};

function parseValue(value: string): number | null | undefined {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= MAX_OUTCOME_VALUE ? parsed : undefined;
}

export function outcomeDraftIsValid(outcome: OutcomeDraft, reason: string, value: string): boolean {
  if (outcome === "lost" && !LOSS_REASONS.includes(reason as LossReason)) return false;
  return parseValue(value) !== undefined;
}

export function buildOutcomePayload(outcome: OutcomeDraft, reason: string, value: string): OutcomePayload {
  const parsedValue = parseValue(value);
  if (parsedValue === undefined || !outcomeDraftIsValid(outcome, reason, value)) {
    throw new Error("Invalid outcome draft");
  }
  return {
    outcome: outcome === "pending" ? null : outcome,
    reason: outcome === "lost" ? reason : "",
    value: parsedValue,
  };
}
