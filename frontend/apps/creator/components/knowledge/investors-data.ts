/** Labelled sample for the Investors knowledge block (five-day sprint brief). */

export const INVESTORS_BLOCK = {
  id: "investors",
  name: "Investors",
  kind: "Knowledge block",
  agents: 3,
  valueThisMonth: "£42.6k",
  valueHint: "Illustrative · value from knowledge used this month.",
  conversations: 186,
  patternsToDate: 24,
  handedToCrm: 11,
};

export const FUNNEL_STEPS = [
  { id: "crm", label: "In CRM", count: 4180, system: "Client CRM · not connected", connected: false },
  { id: "aware", label: "Aware", count: 912, system: "Investor app", connected: true },
  { id: "intent", label: "Intent", count: 28, system: "Intelligence Worker", connected: true, actOn: true },
  { id: "meeting", label: "Meeting", count: 9, system: "Advisor calendar", connected: true },
];

export const BLOCK_AGENTS = [
  {
    id: "intent-intelligence",
    name: "Intelligence Worker",
    role: "Intent & reachouts",
    talkingNow: 3,
    thisMonth: 64,
    toCrm: 8,
    connections: "Investor app · Knowledge library",
    workflow: "Flag intent → recommend → person decides",
  },
  {
    id: "research",
    name: "Research Desk",
    role: "Grounded listing answers",
    talkingNow: 1,
    thisMonth: 41,
    toCrm: 0,
    connections: "Knowledge library · Grounded chat",
    workflow: "Answer only from attached documents",
  },
  {
    id: "quiet-watch",
    name: "Quiet Watch",
    role: "Absence signals",
    talkingNow: 0,
    thisMonth: 12,
    toCrm: 0,
    connections: "Investor app",
    workflow: "Record 7-day quiet listings · no chase",
  },
];

export const CAPTURED_KNOWLEDGE = [
  {
    id: "lombe",
    title: "Lombe House intent supports a referral reachout",
    evidence: "Repeat views flagged interest. A person should decide. Nothing was sent.",
  },
  {
    id: "wall",
    title: "No outbound investor email",
    evidence: "Hard wall. Recorded every time a cluster is written.",
  },
  {
    id: "quiet",
    title: "A 7-day gap in views is worth recording",
    evidence: "Two listings in the sample week. Too few to make a company rule yet.",
  },
];

export const ANALYTICS_BUBBLES = [
  { id: "lombe", label: "Lombe House intent", size: 72, tone: "growing" as const, used: 18 },
  { id: "referral", label: "Referral reachout", size: 58, tone: "attention" as const, used: 9 },
  { id: "quiet", label: "Quiet listings", size: 44, tone: "established" as const, used: 6 },
  { id: "docs", label: "Document-grounded answers", size: 50, tone: "established" as const, used: 11 },
  { id: "wall", label: "Outbound blocked", size: 40, tone: "established" as const, used: 24 },
  { id: "upsell", label: "Selling up", size: 36, tone: "gap" as const, used: 0, gap: true },
];

export const BUBBLE_DETAIL: Record<string, { from: string; evidence: string }> = {
  lombe: {
    from: "Investor app · Intelligence Worker",
    evidence: "Worked example from the 28 high-intent set. Labelled sample — not the live admin feed.",
  },
  referral: {
    from: "Lombe House intent",
    evidence: "Recommendation awaiting a person. Pulse does not send WhatsApp, email, or CRM deals.",
  },
  quiet: {
    from: "Investor app",
    evidence: "Two listings had no new views in 7 days. Written to the activity feed.",
  },
  docs: {
    from: "Knowledge library",
    evidence: "Operator questions answered only from attached documents.",
  },
  wall: {
    from: "Hard wall",
    evidence: "Connected rule: the worker may not contact an investor.",
  },
  upsell: {
    from: "Gap",
    evidence: "Nothing in the block covers selling-up yet. Dashed bubble = missing knowledge.",
  },
};
