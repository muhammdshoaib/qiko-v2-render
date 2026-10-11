import type { Agent } from "@/lib/api";

export type ShowcaseSlug = "property-insights" | "intent-intelligence";

export type ShowcaseOutcome = {
  title: string;
  detail: string;
  at: string;
  status: "completed" | "attention";
  href?: string;
};

export type ShowcaseWorker = {
  slug: ShowcaseSlug;
  name: string;
  role: string;
  purpose: string;
  status: "ready";
  sample: true;
  liveAgentId?: string;
  liveHref?: string;
  activity: string;
  metrics: { label: string; value: string }[];
  responsibilities: string[];
  capabilities: string[];
  sources: { name: string; detail: string }[];
  systems: { name: string; detail: string }[];
  insights: ShowcaseOutcome[];
  actions: ShowcaseOutcome[];
  permissions: { name: string; mode: "allowed" | "requires review" | "blocked" }[];
  intelligence: string;
};

export const COMPANY_SUMMARY = {
  headline: "Two deployed workers are contributing to company intelligence.",
  points: [
    { label: "Active workers", value: "2" },
    { label: "Insights this week", value: "6" },
    { label: "Awaiting review", value: "1" },
    { label: "Knowledge sources", value: "5" },
  ],
};

export const ATTENTION: ShowcaseOutcome[] = [
  {
    title: "Intent spike needs a human look",
    detail: "Lombay House / Derby attracted repeated investor views. The Intelligence Worker flagged it — no outreach was sent.",
    at: "Today, 09:40",
    status: "attention",
    href: "/studio/w/intent-intelligence",
  },
];

export const RECENT_ACTIONS: ShowcaseOutcome[] = [
  {
    title: "Property risk note published",
    detail: "Property Insights summarised expenditure drift on a high-cost unit. Sample from the finance cockpit capability.",
    at: "Today, 08:15",
    status: "completed",
    href: "/studio/w/property-insights",
  },
  {
    title: "Intent signal captured",
    detail: "Intelligence Worker recorded a cluster of investor-app views. Sample from existing intent-signal capability.",
    at: "Yesterday, 16:22",
    status: "completed",
    href: "/studio/w/intent-intelligence",
  },
];

export const SHOWCASE_WORKERS: ShowcaseWorker[] = [
  {
    slug: "property-insights",
    name: "Property Insights",
    role: "Portfolio and property analyst",
    purpose: "Read property, unit, and expenditure records so operators can see income, cost, and risk without building a new report each time.",
    status: "ready",
    sample: true,
    activity: "Last outcome 08:15",
    metrics: [
      { label: "Properties watched", value: "12" },
      { label: "Risk notes", value: "3" },
      { label: "Last run", value: "08:15" },
      { label: "Approvals", value: "0 open" },
    ],
    responsibilities: [
      "Summarise income, spend, and net position by property",
      "Surface units or vendors that drift from the usual pattern",
      "Keep a readable trail of completed finance insights",
    ],
    capabilities: [
      "Finance analytics already used in the Studio finance cockpit",
      "Property and expenditure breakdowns",
      "Grounded chat against uploaded finance files",
    ],
    sources: [
      { name: "Finance uploads", detail: "Spreadsheets the operator attached to this worker." },
      { name: "Property ledger", detail: "Existing property / unit / vendor views in Studio." },
    ],
    systems: [
      { name: "Studio finance cockpit", detail: "Where live numbers are inspected when a finance worker is deployed." },
      { name: "Company intelligence", detail: "Accepted notes become part of the shared record." },
    ],
    insights: [
      { title: "Expenditure drift", detail: "One unit is running above the recent spend band.", at: "Today, 08:15", status: "completed" },
      { title: "Income snapshot", detail: "Portfolio income held flat week-on-week.", at: "Mon, 11:02", status: "completed" },
    ],
    actions: [
      { title: "Risk note written", detail: "Operator-readable summary, not an automated vendor payment.", at: "Today, 08:15", status: "completed" },
    ],
    permissions: [
      { name: "Read property and spend figures", mode: "allowed" },
      { name: "Draft a risk note", mode: "allowed" },
      { name: "Change invoices or pay a vendor", mode: "blocked" },
    ],
    intelligence: "Property Insights contributes portfolio facts — income, cost, and risk — so company intelligence is not only sales or intent noise.",
  },
  {
    slug: "intent-intelligence",
    name: "Intelligence Worker",
    role: "Intent signals and research",
    purpose: "Watch investor and research activity, cluster intent signals, and keep a grounded view of what people are looking at.",
    status: "ready",
    sample: true,
    activity: "Last outcome yesterday, 16:22",
    metrics: [
      { label: "Signals this week", value: "18" },
      { label: "Clusters", value: "4" },
      { label: "Needs review", value: "1" },
      { label: "Sources", value: "3" },
    ],
    responsibilities: [
      "Capture intent signals from existing investor-activity paths",
      "Group repeat attention on a property or development",
      "Answer grounded research questions from attached knowledge",
    ],
    capabilities: [
      "Intelligence cockpit research, sources, and overview",
      "Intent-signal style clustering already described in Joseph Mews modules",
      "Grounded chat with critic + gate",
    ],
    sources: [
      { name: "Knowledge library", detail: "Documents attached to the intelligence worker." },
      { name: "Investor activity", detail: "Existing intent-signal generation, when that worker is linked." },
    ],
    systems: [
      { name: "Studio intelligence cockpit", detail: "Research, sources, and engagement tabs." },
      { name: "Company intelligence", detail: "Flagged clusters land in the shared activity feed." },
    ],
    insights: [
      { title: "Repeat views on Lombay House", detail: "Same development watched several times in one session.", at: "Today, 09:40", status: "attention" },
      { title: "Quiet developments", detail: "Two listings had no new intent in 7 days.", at: "Yesterday, 16:22", status: "completed" },
    ],
    actions: [
      { title: "Signal recorded", detail: "Written to the activity feed. No investor email was sent.", at: "Yesterday, 16:22", status: "completed" },
    ],
    permissions: [
      { name: "Read intent and knowledge", mode: "allowed" },
      { name: "Flag a cluster for review", mode: "requires review" },
      { name: "Contact an investor", mode: "blocked" },
    ],
    intelligence: "The Intelligence Worker contributes attention and research — what people looked at, and what the knowledge base can safely say about it.",
  },
];

export function workerBySlug(slug: string): ShowcaseWorker | undefined {
  return SHOWCASE_WORKERS.find((worker) => worker.slug === slug);
}

export function attachLiveWorkers(workers: ShowcaseWorker[], agents: Agent[]): ShowcaseWorker[] {
  return workers.map((worker) => {
    if (worker.slug === "property-insights") {
      const live = agents.find((agent) => agent.atype === "finance" && agent.status === "ready");
      return live
        ? { ...worker, liveAgentId: live.id, liveHref: `/studio/${live.id}/finance`, name: live.name || worker.name }
        : worker;
    }
    const live = agents.find((agent) => agent.atype === "intelligence" && agent.status === "ready");
    return live
      ? { ...worker, liveAgentId: live.id, liveHref: `/studio/${live.id}/intelligence`, name: live.name || worker.name }
      : worker;
  });
}
