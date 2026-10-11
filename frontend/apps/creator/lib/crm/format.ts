import { STAGE_LABEL, type InvoiceStatus, type PipelineStage } from "./types";

export function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 }).format(value);
}

export function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function daysSince(value: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000));
}

export function timeSince(value: string): string {
  const days = daysSince(value);
  if (days === 0) return "Today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export function isStalled(lastActivityAt: string, stage: PipelineStage): boolean {
  return daysSince(lastActivityAt) >= 7 && stage !== "confirmed" && stage !== "charged";
}

export function invoiceTone(status: InvoiceStatus): string {
  if (status === "paid") return "text-emerald-300";
  if (status === "overdue") return "text-red-300";
  if (status === "partial") return "text-amber-300";
  return "text-slate-300";
}

export function stageLabel(stage: PipelineStage): string {
  return STAGE_LABEL[stage];
}
