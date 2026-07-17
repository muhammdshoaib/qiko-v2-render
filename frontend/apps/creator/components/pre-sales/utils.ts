import type { PackSectionStatus, PackStage } from "@/lib/api";

// Confidence colour bands (grounding %). emerald >= 0.85, amber >= 0.70, red < 0.70 -- these
// classes clear the 4.5:1 contrast bar against the dark cockpit background.
export function confidenceClass(confidence: number): string {
  if (confidence >= 0.85) return "text-emerald-400";
  if (confidence >= 0.7) return "text-amber-400";
  return "text-red-400";
}

export function confidenceBadgeClass(confidence: number): string {
  if (confidence >= 0.85) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (confidence >= 0.7) return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  return "border-red-500/30 bg-red-500/10 text-red-400";
}

export function confidencePct(confidence: number): string {
  return `${Math.round((confidence || 0) * 100)}%`;
}

// Sub-section expand-card metric bands (matches idg.qiko.ai): a 0..1 metric is shown as an integer
// percentage with a colour band -- green >= 80%, amber 60-79%, red < 60%. `metricPct` returns null
// when the metric is missing (nothing drafted yet) so the card can render a neutral placeholder.
export function metricPct(value: number | null | undefined): number | null {
  return value == null ? null : Math.round(value * 100);
}

export function metricBandText(pct: number): string {
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 60) return "text-amber-400";
  return "text-red-400";
}

export function metricBandBar(pct: number): string {
  if (pct >= 80) return "bg-emerald-400";
  if (pct >= 60) return "bg-amber-400";
  return "bg-red-400";
}

// Pill styling for the two idg section-detail metric badges (conf / grounding). Same 80/60 bands
// as the sub-section bars: green >= 80%, amber 60-79%, red < 60%.
export function metricBandBadge(pct: number): string {
  if (pct >= 80) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (pct >= 60) return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  return "border-red-500/30 bg-red-500/10 text-red-400";
}

// Split a free-text gaps string into bullet points on newlines or sentence breaks (". ").
export function splitGaps(gaps: string): string[] {
  return (gaps || "")
    .split(/\r?\n|\.\s+/)
    .map((s) => s.trim().replace(/\.$/, "").trim())
    .filter(Boolean);
}

// Human-readable section status. `manual` sections are IDG-completed (commercial/pricing) sheets,
// not AI-drafted -- surfaced as "IDG commercial" per the cockpit spec.
const SECTION_STATUS_LABELS: Record<PackSectionStatus, string> = {
  not_generated: "Not generated",
  generating: "Generating\u2026",
  draft_ready: "Draft ready",
  reviewing: "In review",
  locked: "Locked",
  manual: "IDG commercial",
  overdue: "Overdue",
};
export function sectionStatusLabel(status: PackSectionStatus): string {
  return SECTION_STATUS_LABELS[status] ?? status;
}

export function sectionStatusBadgeClass(status: PackSectionStatus): string {
  switch (status) {
    case "locked": return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    case "draft_ready": return "border-indigo-500/30 bg-indigo-500/10 text-indigo-400";
    case "reviewing": return "border-violet-500/30 bg-violet-500/10 text-violet-300";
    case "generating": return "border-indigo-500/30 bg-indigo-500/10 text-indigo-300";
    case "manual": return "border-amber-500/30 bg-amber-500/10 text-amber-400";
    case "overdue": return "border-red-500/30 bg-red-500/10 text-red-400";
    default: return "border-slate-500/30 bg-slate-500/10 text-slate-400";
  }
}

// The 5-stage drafting pipeline shown as a progress bar (pack.stage). Order matters: index drives
// completed (< current) / current (==) / future (>) styling.
export const STAGE_ORDER: PackStage[] = ["parsed", "assigned", "drafting", "review", "final"];
export const STAGE_LABELS: Record<PackStage, string> = {
  parsed: "Parsed",
  assigned: "Assigned",
  drafting: "Drafting",
  review: "Review",
  final: "Final",
};

export function wordCount(text: string): number {
  const t = (text || "").trim();
  return t ? t.split(/\s+/).length : 0;
}

export function truncate(text: string, max = 96): string {
  const t = (text || "").trim();
  return t.length > max ? `${t.slice(0, max).trimEnd()}\u2026` : t;
}
