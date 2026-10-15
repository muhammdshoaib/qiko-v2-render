/** Labelled sample for the Investors knowledge block (five-day sprint brief). */

export const INVESTORS_BLOCK = {
  id: "investors",
  name: "Investor Concierge",
  kind: "Knowledge block",
  role: "Intent Signal Agent",
  agents: 1,
  valueThisMonth: "£42.6k",
  valueHint: "Value from knowledge used this month.",
  conversations: 186,
  patternsToDate: 24,
  handedToCrm: 11,
};

export const FUNNEL_STEPS = [
  { id: "crm", label: "In CRM", count: 4180, system: "Client CRM", connected: false },
  { id: "aware", label: "Aware", count: 912, system: "Investor app", connected: true },
  { id: "intent", label: "Intent", count: 28, system: "Investor Concierge", connected: true, actOn: true },
  { id: "meeting", label: "Meeting", count: 9, system: "Advisor calendar", connected: true },
];

/** One knowledge block = one worker (Investor Concierge / Intent Signal Agent). */
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
    systems: ["HubSpot", "Calendly", "Stock sheet", "Rightmove"],
    workflow: "Qualify enquiry → match to stock → book call → hand over to CRM",
    spark: [6, 8, 7, 11, 9, 12, 14, 13, 16, 15, 18, 21],
  },
];

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

export const CAPTURED_KNOWLEDGE = [
  {
    id: "gulf",
    initials: "IC",
    title: "Gulf investors reply 3x faster on WhatsApp after 6pm GST than on email",
    evidence: "Seen in 47 of 61 Gulf conversations",
    when: "2H",
    chip: "Pattern",
    tone: "blue" as const,
    primaryAction: "simulate" as const,
  },
  {
    id: "yield-rule",
    initials: "RS",
    title: "Investors whose first unit passes 6.5% net yield are 4x more likely to buy again within a year",
    evidence: "Back-tested on 112 past investors",
    when: "1D",
    chip: "Proposed rule",
    tone: "warn" as const,
    primaryAction: "rule" as const,
  },
  {
    id: "yield-first",
    initials: "IC",
    title: "A yield question in the first message means a decision within 30 days",
    evidence: "31 of 38 cases, 8 months of data",
    when: "3D",
    chip: "Company rule",
    tone: "good" as const,
    primaryAction: "in_use" as const,
  },
];

export const BLOCK_SUMMARY = {
  updated: "Updated today",
  paragraphs: [
    "Your investors behave like two groups. Gulf investors buy fast, in cash, on WhatsApp, and care about yield. UK investors compare cities and worry about running costs.",
    "Biggest gain this month: referrals from existing investors now convert at twice the rate of portal leads.",
  ],
  risk: "64% of Gulf relationships sit with one adviser (Sarah K.)",
  gap: "No agent covers investors who are selling up",
  next: 'Approve the "ask about cash early" rule',
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
};

/** Investors Analytics tab — sample patterns for the knowledge map (design mock). */
export const ANALYTICS_BUBBLES: AnalyticsBubble[] = [
  {
    id: "referrals",
    label: "Referrals",
    sublabel: "+41% use",
    size: 88,
    tone: "growing",
    used: 41,
    strength: "Pattern · strong",
    agent: "Investor Concierge",
    summary: "Referred investors buy in 38 days instead of 71, and are twice as likely to reach the CRM.",
    stats: [
      { value: "14", label: "referrals behind it" },
      { value: "38 vs 71", label: "days to buy" },
      { value: "64%", label: "reach CRM" },
      { value: "£54k", label: "fees so far" },
    ],
    source: "From HubSpot deals, Xero completions and 47 conversations",
  },
  {
    id: "gulf",
    label: "Gulf investors",
    sublabel: "WhatsApp, evenings",
    size: 64,
    tone: "established",
    used: 22,
    strength: "Pattern · steady",
    agent: "Investor Concierge",
    summary: "Gulf investors prefer WhatsApp in the evening. Replies outside that window get ignored more often.",
    stats: [
      { value: "59", label: "active relationships" },
      { value: "8–11pm", label: "best reply window" },
      { value: "2.1×", label: "reply rate lift" },
      { value: "12", label: "at risk if Sarah leaves" },
    ],
    source: "From adviser WhatsApp samples and calendar replies",
  },
  {
    id: "offplan",
    label: "Off-plan",
    sublabel: "5% deposit",
    size: 42,
    tone: "established",
    used: 11,
    strength: "Pattern · emerging",
    agent: "Portfolio Reporter",
    summary: "Investors asking about 5% deposit off-plan units convert faster when the payment schedule is shown early.",
    stats: [
      { value: "31", label: "enquiries" },
      { value: "5%", label: "deposit asked" },
      { value: "9", label: "moved to meeting" },
      { value: "£2.4m", label: "pipeline" },
    ],
    source: "From investor app calculators and HubSpot stages",
  },
  {
    id: "service",
    label: "Service charges",
    sublabel: "rising concern",
    size: 56,
    tone: "attention",
    used: 17,
    strength: "Needs attention",
    agent: "Portfolio Reporter",
    summary: "Service-charge questions are rising. Investors want a clear yearly total before they commit.",
    stats: [
      { value: "44", label: "mentions this month" },
      { value: "+28%", label: "vs last month" },
      { value: "6", label: "deals slowed" },
      { value: "3", label: "docs missing" },
    ],
    source: "From chat transcripts and document requests",
  },
  {
    id: "yield",
    label: "Yield first",
    sublabel: "company rule",
    size: 40,
    tone: "established",
    used: 29,
    strength: "Company rule",
    agent: "Investor Concierge",
    summary: "Ask net yield early. Investors whose first unit passes 6.5% net yield are more likely to buy again.",
    stats: [
      { value: "6.5%", label: "net yield bar" },
      { value: "4×", label: "repeat buy lift" },
      { value: "112", label: "past investors" },
      { value: "Rule", label: "approved" },
    ],
    source: "Back-tested on 112 past investors",
  },
  {
    id: "ready",
    label: "Ready to buy again",
    size: 38,
    tone: "established",
    used: 8,
    strength: "Pattern · emerging",
    agent: "Reinvestment Scout",
    summary: "Existing owners are signalling readiness for a second unit when occupancy and yield stay above plan.",
    stats: [
      { value: "18", label: "candidates" },
      { value: "7", label: "warm this week" },
      { value: "2", label: "meetings booked" },
      { value: "£1.1m", label: "potential" },
    ],
    source: "From portfolio insights and CRM stages",
  },
  {
    id: "selling",
    label: "Selling up",
    sublabel: "not covered",
    size: 36,
    tone: "gap",
    used: 0,
    gap: true,
    strength: "Gap",
    agent: "—",
    summary: "Nothing in this block covers selling-up yet. Dashed bubble = missing knowledge.",
    stats: [
      { value: "0", label: "patterns" },
      { value: "—", label: "evidence" },
      { value: "—", label: "actions" },
      { value: "Gap", label: "status" },
    ],
    source: "No source connected for this topic yet",
  },
];

/** @deprecated Prefer ANALYTICS_BUBBLES[].summary / stats — kept for older imports. */
export const BUBBLE_DETAIL: Record<string, { from: string; evidence: string }> = Object.fromEntries(
  ANALYTICS_BUBBLES.map((b) => [b.id, { from: b.agent ?? "", evidence: b.summary }]),
);
