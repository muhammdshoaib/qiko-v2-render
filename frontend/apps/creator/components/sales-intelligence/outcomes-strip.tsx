"use client";

// Re-export of the shared cockpit metric strip. The canonical implementation now lives in
// @/components/cockpit/outcomes-strip so the Sales Intelligence and Pre-Sales cockpits share one
// treatment; this thin re-export keeps existing Sales Intelligence page imports stable.
export { OutcomesStrip, type OutcomeTile } from "@/components/cockpit/outcomes-strip";
