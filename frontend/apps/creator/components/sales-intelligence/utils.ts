import type { OpportunityStage, Recommendation } from "@/lib/api";

export function formatMoney(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined) return "\u2014";
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "GBP", maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${currency ?? ""} ${value.toLocaleString()}`.trim();
  }
}

export function formatCompact(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === 0) return "\u2014";
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "GBP", notation: "compact", maximumFractionDigits: 1 }).format(value);
  } catch {
    return formatMoney(value, currency);
  }
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "\u2014";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "\u2014";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) +
    (withTime ? `, ${d.toLocaleTimeString("en-GB", { hour: "numeric", minute: "2-digit" })}` : "");
}

export const STAGE_LABELS: Record<OpportunityStage, string> = {
  ingested: "Ingested",
  qualifying: "Qualifying",
  qualified: "Qualified",
  awaiting_review: "Awaiting Review",
  validated: "Validated",
  ready_salesforce: "Ready for SF",
  push_pending: "Push Pending",
  pushed: "Pushed",
  rejected: "Rejected",
  push_failed: "Push Failed",
};

export const KANBAN_STAGES: OpportunityStage[] = ["ingested", "qualifying", "qualified", "validated", "pushed"];

export function stageBadgeClass(stage: OpportunityStage): string {
  switch (stage) {
    case "awaiting_review": return "border-amber-500/30 bg-amber-500/10 text-amber-400";
    case "validated":
    case "pushed":
    case "ready_salesforce": return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    case "rejected":
    case "push_failed": return "border-red-500/30 bg-red-500/10 text-red-400";
    case "qualified":
    case "qualifying": return "border-indigo-500/30 bg-indigo-500/10 text-indigo-400";
    default: return "border-slate-500/30 bg-slate-500/10 text-slate-400";
  }
}

export function recommendationBadgeClass(rec: Recommendation | null | undefined): string {
  if (rec === "Bid") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (rec === "No Bid") return "border-red-500/30 bg-red-500/10 text-red-400";
  return "border-amber-500/30 bg-amber-500/10 text-amber-400";
}

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#64748b";
  if (score >= 70) return "#34d399";
  if (score >= 40) return "#fbbf24";
  return "#f87171";
}
