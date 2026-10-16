/** Demo insights from Joseph Mews investor app / CMS-shaped fixtures. */

export type InsightStatus = "new" | "reviewed" | "acted";
export type ActionStatus = "pending" | "in_progress" | "completed";

export type PulseInvestor = {
  id: string;
  name: string;
  initials: string;
  segment: string;
  lastActive: string;
  conversations: number;
  insightCount: number;
};

export type PulseInsight = {
  id: string;
  investorId: string;
  title: string;
  summary: string;
  detail: string;
  evidence: string[];
  source: string;
  worker: string;
  when: string;
  status: InsightStatus;
};

export type PulseAction = {
  id: string;
  title: string;
  insightId: string;
  investorId: string;
  status: ActionStatus;
  owner: string;
  due: string;
};

export const PULSE_INVESTORS: PulseInvestor[] = [
  {
    id: "inv-lombe-01",
    name: "Aisha Rahman",
    initials: "AR",
    segment: "Gulf · cash buyer",
    lastActive: "Today, 09:38",
    conversations: 4,
    insightCount: 3,
  },
  {
    id: "inv-4821",
    name: "James Okonkwo",
    initials: "JO",
    segment: "UK · multi-city",
    lastActive: "Yesterday",
    conversations: 2,
    insightCount: 2,
  },
  {
    id: "inv-gulf-07",
    name: "Khalid Al-Harbi",
    initials: "KA",
    segment: "Gulf · WhatsApp",
    lastActive: "2 days ago",
    conversations: 6,
    insightCount: 2,
  },
  {
    id: "inv-ref-12",
    name: "Priya Mehta",
    initials: "PM",
    segment: "Referral",
    lastActive: "Today, 07:12",
    conversations: 1,
    insightCount: 1,
  },
];

export const PULSE_INSIGHTS: PulseInsight[] = [
  {
    id: "ins-lombe-intent",
    investorId: "inv-lombe-01",
    title: "High intent · Lombe House",
    summary: "Repeat views clustered as purchase interest. No outreach sent.",
    detail:
      "Aisha opened Lombe House / Derby three times today and stepped into the calculator. Investor Concierge labelled this as high intent from investor-app activity. Nothing was sent automatically.",
    evidence: [
      "Property viewed · Lombe House / Derby — Today, 09:38",
      "Calculator step opened",
      "Investor app activity (JM CMS)",
    ],
    source: "Joseph Mews investor app",
    worker: "Investor Concierge",
    when: "Today, 09:40",
    status: "new",
  },
  {
    id: "ins-lombe-whatsapp",
    investorId: "inv-lombe-01",
    title: "Prefers WhatsApp after 6pm GST",
    summary: "Replies 3× faster on WhatsApp after 6pm than on email.",
    detail:
      "Pattern from Gulf conversations: evening WhatsApp gets a response; daytime email does not. Useful when a person chooses how to follow up.",
    evidence: ["Seen across Gulf conversations", "Investor Concierge pattern"],
    source: "Conversation history",
    worker: "Investor Concierge",
    when: "2H",
    status: "reviewed",
  },
  {
    id: "ins-lombe-cash",
    investorId: "inv-lombe-01",
    title: "Ask about cash early",
    summary: "Yield-first questions correlate with a decision inside 30 days.",
    detail:
      "When the first message asks about yield, close rates improve. Suggest asking about cash early — a person still decides whether to message.",
    evidence: ["31 of 38 cases over 8 months", "Proposed follow-up for adviser"],
    source: "Investor Concierge",
    worker: "Investor Concierge",
    when: "Today",
    status: "new",
  },
  {
    id: "ins-jo-concentration",
    investorId: "inv-4821",
    title: "Concentration · 3 holdings in London",
    summary: "Grounded card written into the investor app. Not advice.",
    detail:
      "Portfolio Reporter read James’s holdings and wrote a concentration card: three properties in London. Empty portfolios stay empty. No contact or trade advice.",
    evidence: ["3 holdings · London", "Investor portfolios (JM CMS)", "Card delivered in investor app"],
    source: "Joseph Mews investor portfolios",
    worker: "Portfolio Reporter",
    when: "Today, 08:15",
    status: "acted",
  },
  {
    id: "ins-jo-regional",
    investorId: "inv-4821",
    title: "Regional mix across 2 cities",
    summary: "Multi-city holdings summarised for the investor app.",
    detail: "Holdings sit in London and Manchester. Regional card written from portfolio geography only.",
    evidence: ["2 cities tracked", "Portfolio Reporter"],
    source: "Investor portfolios",
    worker: "Portfolio Reporter",
    when: "Yesterday",
    status: "reviewed",
  },
  {
    id: "ins-ka-gulf",
    investorId: "inv-gulf-07",
    title: "Relationship concentration risk",
    summary: "Primary adviser relationship sits with one person.",
    detail:
      "Most of Khalid’s thread history is with a single adviser. Spreading the relationship reduces knowledge loss if that person leaves.",
    evidence: ["Conversation ownership", "Company intelligence"],
    source: "Investor Concierge",
    worker: "Investor Concierge",
    when: "Yesterday",
    status: "new",
  },
  {
    id: "ins-ka-referral",
    investorId: "inv-gulf-07",
    title: "Referral path warmer than portal",
    summary: "Referred investors close faster than portal leads.",
    detail: "Referral programme pattern: referred investors close in ~38 days vs ~71 for portal. For Khalid’s network, a person may choose a soft ask.",
    evidence: ["Referral vs portal pattern", "Pulse insight"],
    source: "Investor Concierge",
    worker: "Investor Concierge",
    when: "Today",
    status: "new",
  },
  {
    id: "ins-pm-referral",
    investorId: "inv-ref-12",
    title: "Referral reachout awaiting a person",
    summary: "1 of 9 labelled reachouts still needs a decision.",
    detail:
      "Priya arrived via referral. A labelled reachout is ready, but nothing is sent until a person approves or declines.",
    evidence: ["Referral label", "Awaiting decision"],
    source: "Investor Concierge",
    worker: "Investor Concierge",
    when: "Today, 07:12",
    status: "new",
  },
];

export const INITIAL_PULSE_ACTIONS: PulseAction[] = [
  {
    id: "act-1",
    title: "Review Lombe House follow-up with Aisha",
    insightId: "ins-lombe-intent",
    investorId: "inv-lombe-01",
    status: "pending",
    owner: "You",
    due: "Today",
  },
  {
    id: "act-2",
    title: "Confirm concentration card seen in app (James)",
    insightId: "ins-jo-concentration",
    investorId: "inv-4821",
    status: "in_progress",
    owner: "Adviser",
    due: "This week",
  },
  {
    id: "act-3",
    title: "Decide referral reachout for Priya",
    insightId: "ins-pm-referral",
    investorId: "inv-ref-12",
    status: "pending",
    owner: "You",
    due: "Today",
  },
];

export function insightsForInvestor(investorId: string) {
  return PULSE_INSIGHTS.filter((i) => i.investorId === investorId);
}

export function investorById(id: string) {
  return PULSE_INVESTORS.find((i) => i.id === id);
}

export function insightById(id: string) {
  return PULSE_INSIGHTS.find((i) => i.id === id);
}
