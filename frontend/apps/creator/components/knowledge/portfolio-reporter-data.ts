/** Portfolio Reporter knowledge block — Portfolio Insights worker. */

import type { HonestyKind } from "@/components/intelligence-layer/model";
import type { AnalyticsBubble } from "./investors-data";

export const PORTFOLIO_BLOCK = {
  id: "portfolio-reporter",
  name: "Portfolio Reporter",
  kind: "Knowledge block",
  role: "Portfolio Insights",
  agents: 1,
  initials: "PR",
  valueThisMonth: "£12.1k",
  valueHint: "Illustrative value for the demo walkthrough.",
  portfoliosWithInsights: 3104,
  holdingsRead: 2140,
  concentrationCards: 412,
  advisedInvestors: 4180,
};

export const PORTFOLIO_FUNNEL = [
  {
    id: "advised",
    label: "Advised investors",
    count: 4180,
    system: "Client register",
    honesty: "illustrative" as HonestyKind,
    connected: false,
  },
  {
    id: "readable",
    label: "Holdings read",
    count: 2140,
    system: "Investor portfolios",
    honesty: "illustrative" as HonestyKind,
    connected: true,
  },
  {
    id: "insights",
    label: "With insights",
    count: 3104,
    system: "Portfolio Reporter",
    honesty: "illustrative" as HonestyKind,
    connected: true,
    actOn: true,
  },
  {
    id: "concentration",
    label: "Concentration cards",
    count: 412,
    system: "Investor app",
    honesty: "illustrative" as HonestyKind,
    connected: true,
  },
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

export type PortfolioOverviewInsight = {
  id: string;
  initials: string;
  title: string;
  evidence: string;
  when: string;
  chip: string;
  tone: "blue" | "warn" | "good";
  detail: string;
  evidenceLines: string[];
  recommendation: string;
  honesty: HonestyKind;
};

export const PORTFOLIO_CAPTURED: PortfolioOverviewInsight[] = [
  {
    id: "concentration",
    initials: "PR",
    title: "412 concentration cards written for advised investors",
    evidence: "3+ holdings in one city · grounded in client portfolios",
    when: "Today",
    chip: "Insight",
    tone: "blue",
    detail:
      "Advised investors with three or more holdings in one city received a concentration card in their app. Portfolio Reporter wrote the card — it did not contact anyone or advise a trade.",
    evidenceLines: [
      "412 concentration cards · investor app",
      "Largest cluster · London",
      "0 outreach sent automatically",
    ],
    recommendation: "Review concentration evidence, then add a human follow-up if a person should act.",
    honesty: "illustrative",
  },
  {
    id: "empty",
    initials: "PR",
    title: "Empty portfolios stay empty — no invented cards",
    evidence: "Hard wall on fabricating holdings",
    when: "Today",
    chip: "Guardrail",
    tone: "good",
    detail:
      "Investors with no readable holdings get no card. This is intentional product behaviour — not a gap to fill with invented data.",
    evidenceLines: ["0 invented cards", "Hard wall · fabricate holdings", "Empty portfolios stay empty"],
    recommendation: "Keep empty portfolios empty — do not invent cards.",
    honesty: "illustrative",
  },
  {
    id: "holdings",
    initials: "PR",
    title: "2,140 client holdings read as input to insight generation",
    evidence: "Not Joseph Mews stock — advised clients’ properties",
    when: "Yesterday",
    chip: "Insight",
    tone: "blue",
    detail:
      "Client holdings are input only. Portfolio Reporter reads them to write grounded cards; it does not edit holdings or move money.",
    evidenceLines: ["2,140 holdings read", "Input only — not JM stock", "0 vendor payments"],
    recommendation: "Use holdings evidence when preparing an adviser conversation — no automated outreach.",
    honesty: "illustrative",
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
    recommendation: "Review concentration evidence, then add a human follow-up if a person should act.",
    honesty: "illustrative" as const,
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
    recommendation: "Use regional evidence when preparing an adviser conversation — no automated outreach.",
    honesty: "illustrative" as const,
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
    recommendation: "Only discuss income when supported inputs exist; never invent forecasts.",
    honesty: "illustrative" as const,
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
    recommendation: "Confirm which pipeline cards still need a person before any follow-up.",
    honesty: "illustrative" as const,
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
    recommendation: "Keep empty portfolios empty — do not invent cards.",
    honesty: "illustrative" as const,
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
