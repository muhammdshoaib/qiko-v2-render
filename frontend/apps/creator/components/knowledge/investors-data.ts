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

/** Labelled demo systems for the overview flow — not live connectors. */
export const BLOCK_SYSTEMS = [
  "HubSpot",
  "Calendly",
  "Stock sheet",
  "Rightmove",
  "Xero",
  "Arthur Online",
  "Google Drive",
  "Deal pipeline",
  "Land Registry",
];

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
};

/** Lean evidence-backed patterns — no invented lift percentages or speculative fee totals. */
export const ANALYTICS_BUBBLES: AnalyticsBubble[] = [
  {
    id: "intent",
    label: "High intent",
    sublabel: "Repeat views",
    size: 72,
    tone: "growing",
    used: 28,
    strength: "Insight",
    agent: "Investor Concierge",
    summary:
      "Repeat property views plus calculator use are labelled as high intent. Supporting activity is listed so a person can decide next steps.",
    stats: [
      { value: "28", label: "intent signals" },
      { value: "3", label: "awaiting review" },
      { value: "0", label: "auto-sent" },
      { value: "App", label: "primary source" },
    ],
    source: "Investor app activity samples",
    recommendation: "Open the insight, view evidence, then add a human follow-up if needed.",
    honesty: "illustrative",
  },
  {
    id: "gulf",
    label: "Gulf timing",
    sublabel: "Evening replies",
    size: 56,
    tone: "established",
    used: 22,
    strength: "Insight",
    agent: "Investor Concierge",
    summary:
      "Sample conversations show stronger reply rates on WhatsApp after 6pm GST. Evidence only — not a campaign rule.",
    stats: [
      { value: "Sample", label: "conversation set" },
      { value: "6pm+", label: "GST window" },
      { value: "Human", label: "sends only" },
      { value: "—", label: "auto outreach" },
    ],
    source: "Conversation history samples",
    recommendation: "When contacting Gulf investors, prefer the evening window if a person reaches out.",
    honesty: "illustrative",
  },
  {
    id: "yield",
    label: "Yield first",
    sublabel: "Early question",
    size: 48,
    tone: "established",
    used: 18,
    strength: "Insight",
    agent: "Investor Concierge",
    summary:
      "An early yield question correlates with faster decisions in the sample set. Use as guidance for advisers, not an automated workflow.",
    stats: [
      { value: "31/38", label: "sample cases" },
      { value: "~30d", label: "decision window" },
      { value: "Human", label: "follow-up" },
      { value: "—", label: "auto rule" },
    ],
    source: "Conversation samples · 8 months",
    recommendation: "Ask about yield/cash early when a person opens a new enquiry.",
    honesty: "illustrative",
  },
  {
    id: "meetings",
    label: "Meetings",
    sublabel: "Enquiries",
    size: 40,
    tone: "attention",
    used: 9,
    strength: "Needs decision",
    agent: "Investor Concierge",
    summary:
      "Nine labelled enquiries/meetings sit in the funnel. Calendar integration is pending — counts are illustrative until live.",
    stats: [
      { value: "9", label: "labelled" },
      { value: "Pending", label: "calendar feed" },
      { value: "0", label: "auto-booked" },
      { value: "Human", label: "confirms" },
    ],
    source: "Advisor calendar · pending integration",
    recommendation: "Confirm which enquiries still need a person before the next meeting slot.",
    honesty: "pending",
  },
];

/** @deprecated Prefer ANALYTICS_BUBBLES[].summary / stats — kept for older imports. */
export const BUBBLE_DETAIL: Record<string, { from: string; evidence: string }> = Object.fromEntries(
  ANALYTICS_BUBBLES.map((b) => [b.id, { from: b.agent ?? "", evidence: b.summary }]),
);

/** CRM-oriented Analytics KPI row — each value carries an honesty label. */
export const ANALYTICS_BUSINESS_KPIS = [
  { label: "Total investors", value: "4,180", hint: "Customer base", honesty: "illustrative" as HonestyKind },
  { label: "App-aware", value: "912", hint: "Investor app users", honesty: "pending" as HonestyKind },
  { label: "High-intent", value: "28", hint: "Intent signals this period", honesty: "illustrative" as HonestyKind },
  { label: "Enquiries / meetings", value: "9", hint: "Advisor calendar", honesty: "pending" as HonestyKind },
];
