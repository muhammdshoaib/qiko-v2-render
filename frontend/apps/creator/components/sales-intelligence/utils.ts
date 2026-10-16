import type { OpportunityStage, Recommendation } from "@/lib/api";

export function formatMoney(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined) return "-";
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "GBP", maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${currency ?? ""} ${value.toLocaleString()}`.trim();
  }
}

export function formatCompact(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === 0) return "-";
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "GBP", notation: "compact", maximumFractionDigits: 1 }).format(value);
  } catch {
    return formatMoney(value, currency);
  }
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
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
    case "awaiting_review": return "border-amber-500/30 bg-amber-50 text-amber-700";
    case "validated":
    case "pushed":
    case "ready_salesforce": return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700";
    case "rejected":
    case "push_failed": return "border-red-500/30 bg-red-500/10 text-red-400";
    case "qualified":
    case "qualifying": return "border-indigo-500/30 bg-indigo-500/10 text-indigo-400";
    default: return "border-slate-500/30 bg-slate-500/10 text-slate-400";
  }
}

export function recommendationBadgeClass(rec: Recommendation | null | undefined): string {
  if (rec === "Bid") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700";
  if (rec === "No Bid") return "border-red-500/30 bg-red-500/10 text-red-400";
  return "border-amber-500/30 bg-amber-50 text-amber-700";
}

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#64748b";
  if (score >= 70) return "#34d399";
  if (score >= 40) return "#fbbf24";
  return "#f87171";
}

// Badge classes for a 0-100 qualification score (mirrors scoreColor bands) -- used on pipeline
// cards / list so the score reads at a glance, at >= 4.5:1 contrast on the dark cockpit.
export function scoreBadgeClass(score: number | null | undefined): string {
  if (score === null || score === undefined) return "border-slate-500/30 bg-slate-500/10 text-slate-400";
  if (score >= 70) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700";
  if (score >= 40) return "border-amber-500/30 bg-amber-50 text-amber-700";
  return "border-red-500/30 bg-red-500/10 text-red-400";
}

// Source keys are portal acronyms (TED = Tenders Electronic Daily, UNGM = UN Global Marketplace),
// so they read best fully upper-cased rather than title-cased.
export function sourceLabel(sourceKey: string | null | undefined): string {
  return (sourceKey || "").toUpperCase() || "-";
}

// Turn a raw enum/slug ("push_failed", "awaiting_review") into human Title Case for display.
export function humanize(value: string | null | undefined): string {
  if (!value) return "-";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Whole days from now until an ISO date. Negative = already past. null when no/invalid date.
export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return Math.ceil((d.getTime() - Date.now()) / 86400000);
}

// Relative deadline copy ("in 5 days", "Today", "3 days ago") for the deadline queue.
export function deadlineLabel(value: string | null | undefined): string {
  const days = daysUntil(value);
  if (days === null) return "-";
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days > 1) return `In ${days} days`;
  if (days === -1) return "1 day overdue";
  return `${Math.abs(days)} days overdue`;
}

// Urgency colour for a deadline: red <= 7 days (or overdue), amber <= 14, slate otherwise.
export function deadlineUrgencyClass(value: string | null | undefined): string {
  const days = daysUntil(value);
  if (days === null) return "text-slate-400";
  if (days <= 7) return "text-red-400";
  if (days <= 14) return "text-amber-700";
  return "text-slate-400";
}
