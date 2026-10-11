export type HonestyKind = "live" | "connected" | "illustrative" | "planned";
export type WorkerId = "crm-agent";
export type SystemId = "crm" | "claude" | "slack-sales" | "slack-revenue" | "email";
export type FocusId = WorkerId | SystemId | "record";
export type EdgeKind = "read" | "write" | "review" | "blocked" | "handoff";
export type ActivityFilter = "all" | "allowed" | "blocked" | "approval" | "completed";
export type CockpitTab = "intelligence" | "observability" | "train" | "sources" | "connections" | "settings";
export type EdgeId =
  | "agent-record"
  | "agent-crm-read"
  | "agent-crm-write"
  | "agent-claude-read"
  | "agent-claude-review"
  | "agent-slack-sales-read"
  | "agent-slack-sales-blocked"
  | "agent-slack-revenue"
  | "agent-email-review";

export type GraphEdge = {
  id: EdgeId;
  from: FocusId;
  to: FocusId;
  kind: EdgeKind;
  label: string;
  rule: string;
  example: string;
};

export type ActivityItem = {
  id: string;
  title: string;
  detail: string;
  at: string;
  filter: Exclude<ActivityFilter, "all">;
  edgeId: EdgeId;
  focus: FocusId;
};

export const CAPTURED_DECISIONS = 47;
export const MONTHLY_DECISIONS = [
  { month: "Jul", value: 8 },
  { month: "Aug", value: 11 },
  { month: "Sep", value: 14 },
  { month: "Oct", value: 14 },
];

export const CRM_AGENT = {
  id: "crm-agent" as const,
  name: "CRM Agent",
  role: "Sales operations worker",
  purpose: "Keep Qiko’s commercial record accurate: follow-ups, tasks, stage movement, and invoice visibility — inside permission walls.",
  responsibilities: [
    "Watch inactive opportunities and propose follow-up",
    "Create tasks from meeting notes and quiet periods",
    "Propose stage updates for human confirmation",
    "Draft outbound email that cannot send without approval",
  ],
  decisions: CAPTURED_DECISIONS,
  reads: [
    { title: "Qiko CRM", detail: "Companies, leads, tasks, and invoice status the operator is allowed to see." },
    { title: "Claude", detail: "Permitted retrieval of the same CRM facts, scoped to the signed-in user." },
    { title: "Slack #sales-pipeline", detail: "Operational pipeline details only — no amounts or costs." },
    { title: "Slack #revenue", detail: "Financial information for individually authorised users." },
  ],
  tools: [
    { name: "Create follow-up task", mode: "allowed" as const },
    { name: "Read company and invoice status", mode: "allowed" as const },
    { name: "Propose opportunity stage update", mode: "requires review" as const },
    { name: "Send follow-up email", mode: "requires review" as const },
    { name: "Share revenue figures in #sales-pipeline", mode: "blocked" as const },
  ],
  hardWalls: [
    "Financial values and costs are blocked in Slack #sales-pipeline.",
    "Outbound email never sends without human confirmation.",
    "Claude cannot perform writes unless an approved action is confirmed.",
  ],
  runs: [
    { id: "r1", time: "09:14", result: "Inactive Albemarle opportunity flagged. Follow-up task created." },
    { id: "r2", time: "09:22", result: "Stage update for Harrow Street proposed — awaiting sign-off." },
    { id: "r3", time: "10:03", result: "Financial question blocked in #sales-pipeline." },
  ],
};

export const SYSTEMS: Record<SystemId, { name: string; subtitle: string }> = {
  crm: { name: "Qiko CRM", subtitle: "Companies · leads · tasks · invoices" },
  claude: { name: "Claude", subtitle: "Retrieval and approved actions" },
  "slack-sales": { name: "Slack #sales-pipeline", subtitle: "Ops only · money blocked" },
  "slack-revenue": { name: "Slack #revenue", subtitle: "Authorised finance only" },
  email: { name: "Email", subtitle: "Outbound needs confirmation" },
};

export const EDGES: GraphEdge[] = [
  {
    id: "agent-record",
    from: "crm-agent",
    to: "record",
    kind: "handoff",
    label: "Captured decisions",
    rule: "Accepted outcomes are written into the Qiko company record as institutional memory.",
    example: "Follow-up task created for Albemarle is stored as a captured decision.",
  },
  {
    id: "agent-crm-read",
    from: "crm-agent",
    to: "crm",
    kind: "read",
    label: "Reads CRM",
    rule: "May read appropriate company, lead, task, and invoice information.",
    example: "CRM Agent identified an inactive opportunity.",
  },
  {
    id: "agent-crm-write",
    from: "crm-agent",
    to: "crm",
    kind: "write",
    label: "Writes CRM",
    rule: "May create follow-up tasks. Stage changes are proposed, not silently applied.",
    example: "Follow-up task created on Albemarle.",
  },
  {
    id: "agent-claude-read",
    from: "crm-agent",
    to: "claude",
    kind: "read",
    label: "Claude retrieval",
    rule: "Claude may retrieve the same facts the operator is allowed to see.",
    example: "Permitted revenue query completed in #revenue via Claude.",
  },
  {
    id: "agent-claude-review",
    from: "crm-agent",
    to: "claude",
    kind: "review",
    label: "Claude actions",
    rule: "Writes and outbound actions from Claude require approval.",
    example: "Opportunity stage update proposed.",
  },
  {
    id: "agent-slack-sales-read",
    from: "crm-agent",
    to: "slack-sales",
    kind: "read",
    label: "Pipeline ops",
    rule: "Operational pipeline details are allowed in #sales-pipeline.",
    example: "Next-step reminder posted without amounts.",
  },
  {
    id: "agent-slack-sales-blocked",
    from: "crm-agent",
    to: "slack-sales",
    kind: "blocked",
    label: "Money blocked",
    rule: "Financial values and costs are restricted in #sales-pipeline.",
    example: "Financial question blocked in #sales-pipeline.",
  },
  {
    id: "agent-slack-revenue",
    from: "crm-agent",
    to: "slack-revenue",
    kind: "read",
    label: "Authorised finance",
    rule: "Financial information is available to individually authorised users in #revenue.",
    example: "Permitted revenue query completed in #revenue.",
  },
  {
    id: "agent-email-review",
    from: "crm-agent",
    to: "email",
    kind: "review",
    label: "Email confirmation",
    rule: "Outbound follow-ups require human confirmation. Nothing is sent from this prototype.",
    example: "Follow-up email approved.",
  },
];

export const ACTIVITY: ActivityItem[] = [
  { id: "ev3", title: "Stage update proposed", detail: "Harrow Street · Proposal Sent → Confirmed. Secondary playbook sample.", at: "09:22", filter: "approval", edgeId: "agent-claude-review", focus: "claude" },
];

export const SOURCES = [
  { name: "Qiko CRM companies and leads", owner: "Qiko CRM", connected: "CRM Agent", sensitivity: "Commercial", assistant: "Yes, scoped", honesty: "illustrative" as HonestyKind },
  { name: "Tasks and follow-ups", owner: "Qiko CRM", connected: "CRM Agent", sensitivity: "Internal ops", assistant: "Yes, scoped", honesty: "illustrative" as HonestyKind },
  { name: "Invoices and commitments", owner: "Qiko CRM", connected: "CRM Agent", sensitivity: "Financial", assistant: "Authorised surfaces only", honesty: "illustrative" as HonestyKind },
];

export const TABS: { id: CockpitTab; label: string }[] = [
  { id: "intelligence", label: "Intelligence" },
  { id: "observability", label: "Observability" },
  { id: "train", label: "Train" },
  { id: "sources", label: "Sources" },
  { id: "connections", label: "Connections" },
  { id: "settings", label: "Settings" },
];

export const EDGE_KIND_LABEL: Record<EdgeKind, string> = {
  read: "Read",
  write: "Write",
  review: "Needs sign-off",
  blocked: "Blocked",
  handoff: "Hand-off",
};

export const ACTIVITY_FILTERS: { id: ActivityFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "allowed", label: "Allowed" },
  { id: "blocked", label: "Blocked" },
  { id: "approval", label: "Needs sign-off" },
  { id: "completed", label: "Completed" },
];

export const RECORD = {
  name: "Qiko company record",
  purpose: "Institutional memory. Accepted CRM Agent outcomes accumulate here as captured decisions — not a conventional CRM dashboard.",
  rings: "Each ring is one month of captured decisions. Outer rings are more recent.",
};

export const SYSTEM_DETAIL: Record<SystemId, {
  purpose: string;
  allowed: string[];
  approval: string[];
  blocked: string[];
}> = {
  crm: {
    purpose: "Operational system of record for companies, leads, tasks, and invoice status.",
    allowed: ["Read company, lead, task, and invoice information the operator may see", "Create follow-up tasks"],
    approval: ["Opportunity stage updates are proposed, not applied silently"],
    blocked: ["The worker cannot invent invoices or financial totals"],
  },
  claude: {
    purpose: "Permitted retrieval and approval-controlled actions on the same facts the signed-in user can see.",
    allowed: ["Retrieve scoped CRM facts"],
    approval: ["Writes and outbound actions require confirmation"],
    blocked: ["Unapproved writes", "Answers that cross a channel wall"],
  },
  "slack-sales": {
    purpose: "Operational pipeline channel. Useful for next steps — not for money.",
    allowed: ["Operational pipeline details and next-step reminders"],
    approval: [],
    blocked: ["Financial values and costs"],
  },
  "slack-revenue": {
    purpose: "Financial channel for individually authorised users.",
    allowed: ["Outstanding invoices and revenue questions for authorised users"],
    approval: [],
    blocked: ["Sharing those figures back into #sales-pipeline"],
  },
  email: {
    purpose: "Outbound commercial follow-up. Nothing sends from this prototype.",
    allowed: ["Draft follow-up copy"],
    approval: ["Every outbound email needs human confirmation"],
    blocked: ["Autonomous send"],
  },
};

export function filterActivity(items: ActivityItem[], filter: ActivityFilter) {
  if (filter === "all") return items;
  return items.filter((item) => item.filter === filter);
}

export function toActivityItem(event: {
  id: string;
  title: string;
  detail: string;
  at: string;
  filter: Exclude<ActivityFilter, "all">;
  edgeId: string;
  focus: string;
}): ActivityItem {
  return {
    id: event.id,
    title: event.title,
    detail: event.detail,
    at: event.at,
    filter: event.filter,
    edgeId: event.edgeId as EdgeId,
    focus: event.focus as FocusId,
  };
}
