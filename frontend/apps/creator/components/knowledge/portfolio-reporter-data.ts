/** Portfolio Reporter knowledge block — Portfolio Insights worker. */

import type { AnalyticsBubble } from "./investors-data";

export const PORTFOLIO_BLOCK = {
  id: "portfolio-reporter",
  name: "Portfolio Reporter",
  kind: "Knowledge block",
  role: "Portfolio Insights",
  agents: 1,
  initials: "PR",
  valueThisMonth: "£12.1k",
  valueHint: "Value from portfolio insight cards used this month.",
  portfoliosWithInsights: 3104,
  holdingsRead: 2140,
  concentrationCards: 412,
  advisedInvestors: 4180,
};

export const PORTFOLIO_FUNNEL = [
  { id: "advised", label: "Advised investors", count: 4180, system: "Client register · illustrative", connected: false },
  { id: "readable", label: "Insights generated", count: 2140, system: "Investor portfolios", connected: true },
  { id: "insights", label: "With insights", count: 3104, system: "Portfolio Reporter", connected: true, actOn: true },
  { id: "concentration", label: "Concentration cards", count: 412, system: "Investor app", connected: true },
];

export const PORTFOLIO_AGENTS = [
  {
    id: "reporting",
    initials: "PR",
    name: "Portfolio Reporter",
    role: "Portfolio Insights",
    status: "Learning" as const,
    talkingNow: 12,
    thisMonth: 96,
    toCrm: 0,
    learned: 4,
    systems: ["Xero", "Arthur Online", "Google Drive", "Investor app"],
    workflow: "Read holdings → write grounded card → answer follow-ups",
    spark: [4, 4, 5, 5, 6, 6, 7, 7, 7, 8, 8, 9],
  },
];

export const PORTFOLIO_SYSTEMS = [
  "Investor portfolios",
  "Investor app",
  "Xero",
  "Arthur Online",
  "Google Drive",
  "Knowledge library",
];

export const PORTFOLIO_CAPTURED = [
  {
    id: "concentration",
    initials: "PR",
    title: "412 concentration cards written for advised investors",
    evidence: "3+ holdings in one city · grounded in client portfolios",
    when: "Today",
    chip: "Insight",
    tone: "blue" as const,
  },
  {
    id: "empty",
    initials: "PR",
    title: "Empty portfolios stay empty — no invented cards",
    evidence: "Hard wall on fabricating holdings",
    when: "Rule",
    chip: "Company rule",
    tone: "good" as const,
  },
  {
    id: "holdings",
    initials: "PR",
    title: "2,140 client holdings read as input to insight generation",
    evidence: "Not Joseph Mews stock — advised clients’ properties",
    when: "Yesterday",
    chip: "Pattern",
    tone: "blue" as const,
  },
];

export const PORTFOLIO_SUMMARY = {
  updated: "Updated today",
  paragraphs: [
    "Portfolio Reporter reads each advised investor’s holdings and writes grounded insight cards into their app.",
    "It does not contact investors, advise a buy or sell, or move money.",
  ],
  risk: "Cannot present Client CRM 4,180 as a live connected register",
  gap: "Selling-up journeys are not covered by this block",
  next: "Bind live insights GETs when demo investorRefs are ready",
};

export const PORTFOLIO_ANALYTICS_BUBBLES: AnalyticsBubble[] = [
  {
    id: "concentration",
    label: "Concentration",
    sublabel: "3+ in one city",
    size: 88,
    tone: "growing",
    used: 38,
    strength: "Pattern · strong",
    agent: "Portfolio Reporter",
    summary: "Clients with three or more holdings in one city receive a concentration card in their app.",
    stats: [
      { value: "412", label: "cards written" },
      { value: "3,104", label: "portfolios with insights" },
      { value: "London", label: "largest cluster" },
      { value: "0", label: "outreach sent" },
    ],
    source: "From advised investor holdings and investor-app cards",
  },
  {
    id: "regional",
    label: "Regional mix",
    sublabel: "geo spread",
    size: 64,
    tone: "established",
    used: 24,
    strength: "Pattern · steady",
    agent: "Portfolio Reporter",
    summary: "Regional cards summarise where an investor’s holdings sit across cities.",
    stats: [
      { value: "1,890", label: "cards" },
      { value: "12", label: "cities tracked" },
      { value: "64%", label: "multi-city" },
      { value: "0", label: "trades advised" },
    ],
    source: "From portfolio holdings geography",
  },
  {
    id: "income",
    label: "Income view",
    sublabel: "rent grounded",
    size: 52,
    tone: "established",
    used: 18,
    strength: "Pattern · emerging",
    agent: "Portfolio Reporter",
    summary: "Income cards only when supported financial inputs exist — never invented forecasts.",
    stats: [
      { value: "980", label: "income cards" },
      { value: "Supported", label: "inputs only" },
      { value: "0", label: "vendor payments" },
      { value: "Blocked", label: "advice" },
    ],
    source: "From supported financial inputs on holdings",
  },
  {
    id: "pipeline",
    label: "Pipeline cards",
    sublabel: "next steps",
    size: 44,
    tone: "attention",
    used: 12,
    strength: "Needs attention",
    agent: "Portfolio Reporter",
    summary: "Pipeline cards flag grounded next steps inside the investor app — person decides any follow-up.",
    stats: [
      { value: "210", label: "pipeline cards" },
      { value: "41", label: "awaiting person" },
      { value: "0", label: "auto-sent" },
      { value: "App", label: "delivery" },
    ],
    source: "From holdings + app delivery path",
  },
  {
    id: "empty-gap",
    label: "Empty portfolios",
    sublabel: "not covered",
    size: 36,
    tone: "gap",
    used: 0,
    gap: true,
    strength: "Gap",
    agent: "—",
    summary: "Investors with no readable holdings get no card. This is intentional — not a missing metric to invent.",
    stats: [
      { value: "0", label: "invented cards" },
      { value: "—", label: "fabricated yield" },
      { value: "Hard wall", label: "status" },
      { value: "Keep", label: "rule" },
    ],
    source: "Product hard wall",
  },
];

export const PORTFOLIO_OBSERVABILITY = [
  {
    id: "o1",
    kind: "insight" as const,
    title: "3,104 portfolios received insights",
    detail: "Grounded cards written from holdings · empty portfolios stayed empty",
    when: "Today, 07:40",
    investor: "batch",
  },
  {
    id: "o2",
    kind: "insight" as const,
    title: "412 concentration cards",
    detail: "3+ holdings in one city · delivered in investor app",
    when: "Today, 08:15",
    investor: "batch",
  },
  {
    id: "o3",
    kind: "action" as const,
    title: "Client holdings read",
    detail: "2,140 holdings inspected as input — not Joseph Mews stock",
    when: "Yesterday, 15:10",
    investor: "batch",
  },
  {
    id: "o4",
    kind: "blocked" as const,
    title: "Advice and payment blocked",
    detail: "Portfolio Reporter cannot contact an investor, advise a trade, or pay a vendor",
    when: "Today, 08:16",
    investor: "—",
  },
  {
    id: "o5",
    kind: "insight" as const,
    title: "Regional mix card written",
    detail: "Multi-city holdings summarised for one advised investor",
    when: "Yesterday, 11:02",
    investor: "inv-4821",
  },
];
