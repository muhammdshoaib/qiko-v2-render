import type { Agent } from "@/lib/api";
import type { FocusId } from "@/components/intelligence-layer/model";

export type ShowcaseSlug = "property-insights" | "intent-intelligence";

export type ShowcaseOutcome = {
  title: string;
  detail: string;
  at: string;
  status: "completed" | "attention";
  origin: FocusId;
  originLabel: string;
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

export const ATTENTION: ShowcaseOutcome[] = [
  {
    title: "Lombe House intent captured",
    detail: "Lombe House / Derby attracted repeated investor views. Investor Concierge flagged interest — no outreach was sent.",
    at: "Today, 09:40",
    status: "completed",
    origin: "intent-intelligence",
    originLabel: "Investor Concierge",
    href: "/studio/w/intent-intelligence",
  },
];

export const RECENT_ACTIONS: ShowcaseOutcome[] = [
  {
    title: "3,104 portfolios received insights",
    detail: "Portfolio Reporter read each advised investor’s holdings and wrote grounded cards into their app. Empty portfolios got no invented card.",
    at: "Today, 07:40",
    status: "completed",
    origin: "properties",
    originLabel: "Portfolio Reporter",
    href: "/knowledge/portfolio-reporter",
  },
  {
    title: "2,140 client holdings read",
    detail: "Properties those investors own. Input to insight generation — not Joseph Mews stock.",
    at: "Yesterday, 15:10",
    status: "completed",
    origin: "properties",
    originLabel: "Portfolio Reporter",
    href: "/knowledge/portfolio-reporter",
  },
  {
    title: "412 concentration cards",
    detail: "Clients with 3+ holdings in one city. Example: “You have 3 properties in London; this portfolio is not diverse.”",
    at: "Today, 08:15",
    status: "completed",
    origin: "property-insights",
    originLabel: "Portfolio Reporter",
    href: "/knowledge/portfolio-reporter",
  },
  {
    title: "8 reachouts already on the record",
    detail: "Recommended reachouts written after a person decided. Pulse sent none of them.",
    at: "This quarter",
    status: "completed",
    origin: "investor-app",
    originLabel: "Investor Concierge",
    href: "/studio/w/intent-intelligence",
  },
  {
    title: "Intent signal captured",
    detail: "Investor Concierge recorded a cluster of investor-app views.",
    at: "Yesterday, 16:22",
    status: "completed",
    origin: "investor-app",
    originLabel: "Investor Concierge",
    href: "/studio/w/intent-intelligence",
  },
];

export const SHOWCASE_WORKERS: ShowcaseWorker[] = [
  {
    slug: "property-insights",
    name: "Portfolio Reporter",
    role: "Portfolio Insights",
    purpose: "Joseph Mews is the property advisor. For each advised investor, read their portfolio and write grounded insight cards into their app — without contacting anyone, advising a trade, or moving money.",
    status: "ready",
    sample: true,
    activity: "Last outcome 08:15",
    metrics: [
      { label: "Advised investors", value: "4,180" },
      { label: "With insights", value: "3,104" },
      { label: "Holdings read", value: "2,140" },
      { label: "Concentration cards", value: "412" },
    ],
    responsibilities: [
      "Inspect each advised investor’s holdings",
      "Write that investor a grounded card in the app",
      "Count insight types across clients for the operator",
    ],
    capabilities: [
      "Portfolio insight generation already used in the investor app",
      "Concentration, regional, income, and pipeline cards where holdings support them",
      "Grounded chat against attached holdings",
    ],
    sources: [
      { name: "Investor portfolios", detail: "Each advised investor’s holdings. The worker inspects them to ground that investor’s cards." },
      { name: "Investor app", detail: "Where each client already sees their own card." },
    ],
    systems: [
      { name: "Investor app", detail: "Where each investor already sees their own card." },
      { name: "Company intelligence", detail: "Accepted notes become part of the shared record." },
    ],
    insights: [
      { title: "3,104 portfolios received insights", detail: "The worker read client holdings and wrote grounded cards. Empty portfolios stayed empty.", at: "Today, 07:40", status: "completed", origin: "properties", originLabel: "Properties" },
      { title: "412 concentration cards", detail: "Clients with 3+ holdings in one city. Written per investor, counted here.", at: "Today, 08:15", status: "completed", origin: "properties", originLabel: "Properties" },
    ],
    actions: [
      { title: "Client holdings read", detail: "2,140 holdings belong to advised investors. Input to insight generation — not Joseph Mews stock.", at: "Yesterday, 15:10", status: "completed", origin: "property-insights", originLabel: "Portfolio Reporter" },
    ],
    permissions: [
      { name: "Read client portfolios", mode: "allowed" },
      { name: "Write a per-investor insight card", mode: "allowed" },
      { name: "Contact an investor, advise a trade, or pay a vendor", mode: "blocked" },
    ],
    intelligence: "Portfolio Reporter contributes per-investor portfolio insights — what each advised client already holds, and the cards written from that — so company intelligence is not only intent noise.",
  },
  {
    slug: "intent-intelligence",
    name: "Investor Concierge",
    role: "Intent Signal Agent",
    purpose: "Watch investor and research activity, cluster intent signals, and keep a grounded view of what people are looking at.",
    status: "ready",
    sample: true,
    activity: "Last outcome yesterday, 16:22",
    metrics: [
      { label: "Investors on book", value: "4,180" },
      { label: "High-intent", value: "28" },
      { label: "Reachouts this quarter", value: "9" },
      { label: "Needs a person", value: "1" },
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
      { title: "Repeat views on Lombe House", detail: "Same development watched several times in one session.", at: "Today, 09:40", status: "completed", origin: "investor-app", originLabel: "Investors" },
      { title: "Quiet developments", detail: "Two listings had no new intent in 7 days.", at: "Yesterday, 16:22", status: "completed", origin: "investor-app", originLabel: "Investors" },
    ],
    actions: [
      { title: "Signal recorded", detail: "Written to the activity feed. No investor email was sent.", at: "Yesterday, 16:22", status: "completed", origin: "intent-intelligence", originLabel: "Investor Concierge" },
    ],
    permissions: [
      { name: "Read intent and knowledge", mode: "allowed" },
      { name: "Flag a cluster for review", mode: "requires review" },
      { name: "Contact an investor", mode: "blocked" },
    ],
    intelligence: "Investor Concierge contributes attention and research — what people looked at, and what the knowledge base can safely say about it.",
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
