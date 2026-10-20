/** Labelled sample for the Investors knowledge block — honesty labels per Pulse feedback 16 Oct 2026. */

import type { HonestyKind } from "@/components/intelligence-layer/model";

export const INVESTORS_BLOCK = {
  id: "investors",
  name: "Investor Concierge",
  kind: "Knowledge block",
  role: "Intent Signal Agent",
  agents: 1,
  valueThisMonth: "£18.4k",
  valueHint: "Illustrative value for the demo walkthrough.",
  conversations: 186,
  patternsToDate: 24,
  handedToCrm: 11,
};

/** Business stages — customer base → app-aware → intent → enquiries/meetings. */
export const FUNNEL_STEPS = [
  {
    id: "base",
    label: "Customer base",
    count: 4180,
    system: "Client CRM",
    honesty: "illustrative" as HonestyKind,
    connected: false,
  },
  {
    id: "aware",
    label: "App-aware",
    count: 912,
    system: "Investor app",
    honesty: "pending" as HonestyKind,
    connected: true,
  },
  {
    id: "intent",
    label: "Intent signals",
    count: 28,
    system: "Investor Concierge",
    honesty: "illustrative" as HonestyKind,
    connected: true,
    actOn: true,
  },
  {
    id: "meeting",
    label: "Enquiries / meetings",
    count: 9,
    system: "Advisor calendar",
    honesty: "pending" as HonestyKind,
    connected: true,
  },
];

/** One knowledge block = one worker. Systems / destinations are labelled demo paths (Illustrative). */
export const BLOCK_AGENTS = [
  {
    id: "concierge",
    initials: "IC",
    name: "Investor Concierge",
    role: "Intent Signal Agent",
    status: "Learning" as const,
    talkingNow: 38,
    thisMonth: 214,
    toCrm: 23,
    learned: 11,
    knowledgeValue: "£42.6k",
    hoursSaved: "11 HRS SAVED",
    landsIn: { name: "HubSpot", detail: "29 deals · £4.1m" },
    systems: [
      "HubSpot",
      "Calendly",
      "Stock sheet",
      "Rightmove",
      "Xero",
      "Arthur Online",
      "Google Drive",
      "Deal pipeline",
      "Land Registry",
    ],
    workflow: "Observe intent → surface insight → human follow-up",
    spark: [6, 8, 7, 11, 9, 12, 14, 13, 16, 15, 18, 21],
  },
];

/** Labelled demo systems for overview + Connections — not live connectors. */
export const BLOCK_SYSTEM_CONNECTIONS = [
  {
    id: "hubspot",
    name: "HubSpot",
    actions: "CRM deals & contacts · labelled sample reads",
    purpose: "CRM where Investor Concierge lands deals and referral tags in the walkthrough.",
    allowed: ["Read deal and contact samples", "Surface referral and stage evidence"],
    blocked: ["Create or edit live HubSpot records from this demo", "Send investor email from HubSpot"],
  },
  {
    id: "calendly",
    name: "Calendly",
    actions: "Meeting slots · upsell / valuation bookings",
    purpose: "Calendar bookings for adviser meetings shown in the investor journey.",
    allowed: ["Read labelled meeting bookings"],
    blocked: ["Auto-book or cancel meetings", "Message the investor"],
  },
  {
    id: "stock-sheet",
    name: "Stock sheet",
    actions: "Available stock · listing context for intent",
    purpose: "Internal stock sheet used to ground which units are in play.",
    allowed: ["Read available stock samples"],
    blocked: ["Change stock or pricing", "Publish listings"],
  },
  {
    id: "rightmove",
    name: "Rightmove",
    actions: "Portal listings · comparable context",
    purpose: "Portal listing context for walkthrough conversations.",
    allowed: ["Read labelled listing samples"],
    blocked: ["Post or edit live Rightmove ads"],
  },
  {
    id: "xero",
    name: "Xero",
    actions: "Completions & fees · accounting evidence",
    purpose: "Accounting evidence for fees and completions referenced in Analytics patterns.",
    allowed: ["Read labelled completion and fee samples"],
    blocked: ["Create invoices or move money"],
  },
  {
    id: "arthur-online",
    name: "Arthur Online",
    actions: "Property management · rent / yield inputs",
    purpose: "Property-management inputs that ground yield and reinvestment patterns.",
    allowed: ["Read labelled rent and yield samples"],
    blocked: ["Change tenancy or rent in live systems"],
  },
  {
    id: "google-drive",
    name: "Google Drive",
    actions: "Shared docs · statements and packs",
    purpose: "Document store for statements and packs used as supporting evidence.",
    allowed: ["Read attached document samples"],
    blocked: ["Delete or share files outside the tenant"],
  },
  {
    id: "deal-pipeline",
    name: "Deal pipeline",
    actions: "Pipeline stages · human follow-up board",
    purpose: "Internal pipeline board for deals that need a person.",
    allowed: ["Read labelled pipeline stages"],
    blocked: ["Advance stages automatically without a person"],
  },
  {
    id: "land-registry",
    name: "Land Registry",
    actions: "Title / ownership context · sell-to-fund",
    purpose: "Ownership context for sell-to-fund and exit-planner gaps.",
    allowed: ["Read labelled ownership samples"],
    blocked: ["Submit filings or change title"],
  },
] as const;

export const BLOCK_SYSTEMS = BLOCK_SYSTEM_CONNECTIONS.map((c) => c.name);

export type OverviewInsight = {
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

export const CAPTURED_KNOWLEDGE: OverviewInsight[] = [
  {
    id: "lombe-intent",
    initials: "IC",
    title: "High intent · Lombe House",
    evidence: "Repeat views + calculator — investor app activity",
    when: "Today",
    chip: "Insight",
    tone: "blue",
    detail:
      "Aisha opened Lombe House / Derby three times today and stepped into the calculator. Investor Concierge labelled this as high intent. Nothing was sent automatically.",
    evidenceLines: [
      "Property viewed · Lombe House / Derby — Today, 09:38",
      "Calculator step opened",
      "Investor app activity (JM CMS)",
    ],
    recommendation: "Review and decide whether a person should follow up.",
    honesty: "illustrative",
  },
  {
    id: "gulf",
    initials: "IC",
    title: "Gulf investors reply faster on WhatsApp after 6pm GST",
    evidence: "Seen across sample Gulf conversations",
    when: "2H",
    chip: "Insight",
    tone: "blue",
    detail:
      "Evening WhatsApp replies land more often than daytime email in the sample set. Useful context when a person chooses how to follow up — not an automated campaign.",
    evidenceLines: ["Conversation timing pattern", "Investor Concierge sample set"],
    recommendation: "Prefer evening WhatsApp for Gulf follow-ups when a person reaches out.",
    honesty: "illustrative",
  },
  {
    id: "yield-first",
    initials: "IC",
    title: "A yield question early often means a decision within 30 days",
    evidence: "31 of 38 sample cases over 8 months",
    when: "3D",
    chip: "Insight",
    tone: "good",
    detail:
      "When the first message asks about yield, close timing improves in the sample. A person still decides whether to ask about cash early.",
    evidenceLines: ["31 of 38 cases · 8 months", "Conversation history sample"],
    recommendation: "Ask about cash/yield early on new enquiries — human decision only.",
    honesty: "illustrative",
  },
];

export const BLOCK_SUMMARY = {
  updated: "Updated today",
  paragraphs: [
    "Investor Concierge surfaces intent from the investor app and conversation samples.",
    "Follow-ups stay with people. Nothing is sent automatically in this demo.",
  ],
  risk: "Illustrative: relationship concentration patterns need verified live data.",
  gap: "Selling-up coverage is not in this block yet.",
  next: "Add a follow-up from the Lombe House insight on Pulse.",
};

export type AnalyticsBubble = {
  id: string;
  label: string;
  sublabel?: string;
  size: number;
  tone: "growing" | "established" | "attention" | "gap";
  used: number;
  gap?: boolean;
  strength?: string;
  agent?: string;
  summary: string;
  stats: { value: string; label: string }[];
  source: string;
  recommendation: string;
  honesty: HonestyKind;
  /** Open external Claude simulation when true. */
  simulate?: boolean;
  /** Proposed company rule — "Make it a rule" action. */
  rule?: string;
  /** Already adopted as a company rule. */
  inUse?: boolean;
  /** Cover-this-gap CTA for uncovered patterns. */
  workerGap?: boolean;
};

/** Knowledge-map patterns for Investors Analytics (layout aligned to Pulse drill-down reference). */
export const ANALYTICS_BUBBLES: AnalyticsBubble[] = [
  {
    id: "referrals",
    label: "Referrals",
    sublabel: "+41% use",
    size: 100,
    tone: "growing",
    used: 180,
    strength: "Pattern · strong",
    agent: "Investor Concierge",
    summary:
      "Referred investors buy in 38 days instead of 71, and are twice as likely to reach the CRM.",
    stats: [
      { value: "14", label: "referrals behind it" },
      { value: "38 vs 71", label: "days to buy" },
      { value: "64%", label: "reach CRM" },
      { value: "£54k", label: "fees so far" },
    ],
    source: "From HubSpot deals, Xero completions and 47 conversations",
    recommendation: "Ask every new investor who referred them and tag it in HubSpot",
    honesty: "illustrative",
    simulate: true,
    rule: "Ask every new investor who referred them and tag it in HubSpot",
  },
  {
    id: "gulf",
    label: "Gulf investors",
    sublabel: "WhatsApp, evenings",
    size: 78,
    tone: "established",
    used: 120,
    strength: "Pattern",
    agent: "Investor Concierge",
    summary: "Gulf investors reply 3x faster on WhatsApp after 6pm GST than on email.",
    stats: [
      { value: "47 of 61", label: "Gulf chats" },
      { value: "3x", label: "faster replies" },
      { value: "120", label: "uses this month" },
      { value: "64%", label: "sit with Sarah K." },
    ],
    source: "From WhatsApp Business and Gmail",
    recommendation: "Send Gulf investor follow-ups on WhatsApp after 6pm GST",
    honesty: "illustrative",
    rule: "Send Gulf investor follow-ups on WhatsApp after 6pm GST",
  },
  {
    id: "yield",
    label: "Yield first",
    sublabel: "company rule",
    size: 68,
    tone: "established",
    used: 95,
    strength: "Company rule",
    agent: "Investor Concierge",
    summary: "A yield question in the first message means a decision within 30 days.",
    stats: [
      { value: "31 of 38", label: "cases" },
      { value: "8 months", label: "of data" },
      { value: "95", label: "uses this month" },
      { value: "30 days", label: "to decide" },
    ],
    source: "From HubSpot and 38 conversations",
    recommendation: "Ask about yield early — already adopted as a company rule.",
    honesty: "illustrative",
    inUse: true,
  },
  {
    id: "service",
    label: "Service charges",
    sublabel: "rising concern",
    size: 56,
    tone: "attention",
    used: 60,
    strength: "Needs attention",
    agent: "Portfolio Reporter",
    summary:
      "Service charge questions are up 40% since July, mostly from UK investors comparing cities.",
    stats: [
      { value: "22", label: "chats this month" },
      { value: "+40%", label: "since July" },
      { value: "3", label: "paused purchases" },
      { value: "18%", label: "charge rise at one block" },
    ],
    source: "From statements, Gmail and web chat",
    recommendation: "Review service-charge answers before the next UK comparison call.",
    honesty: "illustrative",
    simulate: true,
  },
  {
    id: "ready",
    label: "Ready to buy again",
    sublabel: "6.5% yield",
    size: 50,
    tone: "growing",
    used: 45,
    strength: "Proposed rule",
    agent: "Reinvestment Scout",
    summary:
      "Investors whose first unit passes 6.5% net yield are 4x more likely to buy again within a year.",
    stats: [
      { value: "112", label: "investors back-tested" },
      { value: "4x", label: "more likely" },
      { value: "7", label: "flagged this month" },
      { value: "6.5%", label: "net yield line" },
    ],
    source: "From Xero, Arthur Online and HubSpot",
    recommendation: "Flag investors whose first unit passes 6.5% net yield for a buy-again call",
    honesty: "illustrative",
    rule: "Flag investors whose first unit passes 6.5% net yield for a buy-again call",
  },
  {
    id: "offplan",
    label: "Off-plan",
    sublabel: "5% deposit",
    size: 46,
    tone: "growing",
    used: 40,
    strength: "Pattern",
    agent: "Investor Concierge",
    summary: "Off-plan buyers commit when a 5% deposit option is offered.",
    stats: [
      { value: "9 of 12", label: "reservations" },
      { value: "5%", label: "deposit" },
      { value: "40", label: "uses this month" },
      { value: "Amir S.", label: "waiting on it" },
    ],
    source: "From HubSpot and WhatsApp Business",
    recommendation: "Mention the 5% deposit option in every off-plan reply",
    honesty: "illustrative",
    rule: "Mention the 5% deposit option in every off-plan reply",
  },
  {
    id: "selling",
    label: "Selling up",
    sublabel: "not covered",
    size: 42,
    tone: "gap",
    used: 0,
    gap: true,
    strength: "Gap",
    agent: "—",
    summary:
      "Nothing in this block covers investors who are selling up. 6 sell-to-fund conversations this month went to a person.",
    stats: [
      { value: "6", label: "conversations" },
      { value: "0", label: "agents cover it" },
      { value: "Tom H.", label: "is one of them" },
      { value: "£410k", label: "unit in play" },
    ],
    source: "From HubSpot and Gmail",
    recommendation: "Cover this gap with an Exit Planner worker on your plan.",
    honesty: "illustrative",
    workerGap: true,
  },
];

/** @deprecated Prefer ANALYTICS_BUBBLES[].summary / stats — kept for older imports. */
export const BUBBLE_DETAIL: Record<string, { from: string; evidence: string }> = Object.fromEntries(
  ANALYTICS_BUBBLES.map((b) => [b.id, { from: b.agent ?? "", evidence: b.summary }]),
);

/** Optional CRM KPI strip — hidden on the default Analytics layout. */
export const ANALYTICS_BUSINESS_KPIS = [
  { label: "Total investors", value: "4,180", hint: "Customer base", honesty: "illustrative" as HonestyKind },
  { label: "App-aware", value: "912", hint: "Investor app users", honesty: "pending" as HonestyKind },
  { label: "High-intent", value: "28", hint: "Intent signals this period", honesty: "illustrative" as HonestyKind },
  { label: "Enquiries / meetings", value: "9", hint: "Advisor calendar", honesty: "pending" as HonestyKind },
];

/** Conversations-per-day sample for Today's analytics (last 30 days). */
export const ANALYTICS_CONVERSATIONS_30D = [
  6, 8, 9, 8, 10, 11, 9, 12, 10, 11, 12, 13, 11, 12, 14, 13, 15, 12, 14, 15, 13, 16, 14, 12, 13, 15, 14, 16, 15, 18,
];

/** Handed-to-CRM weekly sample for Today's analytics. */
export const ANALYTICS_CRM_WEEKS = [
  { week: "W1", count: 6 },
  { week: "W2", count: 7 },
  { week: "W3", count: 8 },
  { week: "W4", count: 8 },
];
