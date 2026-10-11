export type HonestyKind = "live" | "connected" | "illustrative" | "planned";
export type WorkerId = "property-insights" | "intent-intelligence";
export type SystemId = "properties" | "investor-app" | "knowledge" | "chat";
export type FocusId = WorkerId | SystemId | "record";
export type EdgeKind = "read" | "write" | "review" | "blocked" | "handoff";
export type ActivityFilter = "all" | "allowed" | "blocked" | "approval" | "completed";
export type CockpitTab = "intelligence" | "observability" | "train" | "sources" | "connections" | "channels" | "settings";
export type EdgeId =
  | "property-record"
  | "intent-record"
  | "property-properties"
  | "property-knowledge"
  | "intent-investor"
  | "intent-knowledge"
  | "intent-chat"
  | "property-chat";

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

export const CAPTURED_DECISIONS = 18;
export const MONTHLY_DECISIONS = [
  { month: "Jul", value: 3 },
  { month: "Aug", value: 4 },
  { month: "Sep", value: 5 },
  { month: "Oct", value: 6 },
];

export const WORKERS: Record<WorkerId, {
  id: WorkerId;
  name: string;
  role: string;
  purpose: string;
  responsibilities: string[];
  reads: { title: string; detail: string }[];
  writes: { title: string; detail: string }[];
  tools: { name: string; mode: "allowed" | "requires review" | "blocked" }[];
  hardWalls: string[];
  runs: { id: string; time: string; result: string }[];
  decisions: number;
}> = {
  "property-insights": {
    id: "property-insights",
    name: "Property Insights",
    role: "Portfolio and property analyst",
    purpose: "Read property and spend records so operators can see income, cost, and risk.",
    responsibilities: [
      "Summarise income, spend, and net position",
      "Flag expenditure drift",
      "Write operator-readable risk notes",
    ],
    reads: [
      { title: "Property records", detail: "Existing finance / property cockpit figures." },
      { title: "Knowledge library", detail: "Uploaded finance files when a finance worker is linked." },
    ],
    writes: [
      { title: "Company intelligence", detail: "Accepted risk notes become part of the shared record." },
    ],
    tools: [
      { name: "Read property figures", mode: "allowed" },
      { name: "Draft a risk note", mode: "allowed" },
      { name: "Pay a vendor or change invoices", mode: "blocked" },
    ],
    hardWalls: [
      "Cannot move money or edit invoices.",
      "Does not contact investors.",
    ],
    runs: [
      { id: "p1", time: "08:15", result: "Expenditure drift note written for a high-cost unit." },
    ],
    decisions: 11,
  },
  "intent-intelligence": {
    id: "intent-intelligence",
    name: "Intelligence Worker",
    role: "Intent signals and research",
    purpose: "Cluster investor attention and answer grounded research questions.",
    responsibilities: [
      "Capture intent signals",
      "Group repeat attention on a listing",
      "Answer from attached knowledge",
    ],
    reads: [
      { title: "Investor activity", detail: "Existing intent-signal paths when linked." },
      { title: "Knowledge library", detail: "Documents on the intelligence worker." },
    ],
    writes: [
      { title: "Company intelligence", detail: "Flagged attention clusters land in the shared record after review." },
    ],
    tools: [
      { name: "Read intent and knowledge", mode: "allowed" },
      { name: "Flag a cluster for review", mode: "requires review" },
      { name: "Contact an investor", mode: "blocked" },
    ],
    hardWalls: [
      "No outbound investor email.",
      "Research answers stay behind the critic + gate.",
    ],
    runs: [
      { id: "i1", time: "09:40", result: "Repeat views on Lombay House flagged for review." },
    ],
    decisions: 7,
  },
};

export const SYSTEMS: Record<SystemId, { name: string; subtitle: string }> = {
  properties: { name: "Property records", subtitle: "Income · spend · risk" },
  "investor-app": { name: "Investor activity", subtitle: "Intent signals" },
  knowledge: { name: "Knowledge library", subtitle: "Uploaded sources" },
  chat: { name: "Grounded chat", subtitle: "Critic + gate" },
};

export const EDGES: GraphEdge[] = [
  {
    id: "property-record",
    from: "property-insights",
    to: "record",
    kind: "handoff",
    label: "Portfolio facts",
    rule: "Accepted property notes become company intelligence.",
    example: "Expenditure drift note added to the shared record.",
  },
  {
    id: "intent-record",
    from: "intent-intelligence",
    to: "record",
    kind: "handoff",
    label: "Intent facts",
    rule: "Flagged attention clusters become company intelligence.",
    example: "Lombay House cluster recorded.",
  },
  {
    id: "property-properties",
    from: "property-insights",
    to: "properties",
    kind: "read",
    label: "Reads properties",
    rule: "May read figures the operator can already see in the finance cockpit.",
    example: "Income snapshot for the watched portfolio.",
  },
  {
    id: "property-knowledge",
    from: "property-insights",
    to: "knowledge",
    kind: "read",
    label: "Reads finance files",
    rule: "Uses uploaded finance documents when present.",
    example: "Vendor spend file used for a drift note.",
  },
  {
    id: "property-chat",
    from: "property-insights",
    to: "chat",
    kind: "read",
    label: "Grounded answers",
    rule: "Chat stays behind critic + gate.",
    example: "Operator asked for net profit on one property.",
  },
  {
    id: "intent-investor",
    from: "intent-intelligence",
    to: "investor-app",
    kind: "read",
    label: "Reads intent",
    rule: "May read existing investor-activity signals.",
    example: "Repeat views clustered on one development.",
  },
  {
    id: "intent-knowledge",
    from: "intent-intelligence",
    to: "knowledge",
    kind: "read",
    label: "Reads research",
    rule: "Answers only from attached knowledge.",
    example: "Grounded question about a listing.",
  },
  {
    id: "intent-chat",
    from: "intent-intelligence",
    to: "chat",
    kind: "review",
    label: "Review flags",
    rule: "Contacting anyone stays blocked; flags need a person.",
    example: "Cluster marked for human review.",
  },
];

export const ACTIVITY: ActivityItem[] = [
  { id: "ev-risk", title: "Property risk note", detail: "Expenditure drift on a high-cost unit.", at: "08:15", filter: "completed", edgeId: "property-record", focus: "property-insights" },
  { id: "ev-intent", title: "Intent cluster flagged", detail: "Lombay House / Derby repeat views.", at: "09:40", filter: "approval", edgeId: "intent-record", focus: "intent-intelligence" },
  { id: "ev-income", title: "Income snapshot", detail: "Portfolio income held flat.", at: "Mon 11:02", filter: "allowed", edgeId: "property-properties", focus: "properties" },
  { id: "ev-pay-block", title: "Vendor payment blocked", detail: "Property Insights cannot change invoices or pay a vendor.", at: "08:16", filter: "blocked", edgeId: "property-properties", focus: "property-insights" },
  { id: "ev-contact-block", title: "Investor email blocked", detail: "The Intelligence Worker cannot contact an investor.", at: "09:41", filter: "blocked", edgeId: "intent-chat", focus: "intent-intelligence" },
];

export const SOURCES = [
  { name: "Finance uploads", owner: "Property Insights", connected: "Property Insights", sensitivity: "Commercial", assistant: "Grounded only", honesty: "illustrative" as HonestyKind },
  { name: "Property ledger", owner: "Studio finance", connected: "Property Insights", sensitivity: "Internal ops", assistant: "Yes, scoped", honesty: "illustrative" as HonestyKind },
  { name: "Investor activity", owner: "Intent paths", connected: "Intelligence Worker", sensitivity: "Behavioural", assistant: "Yes, scoped", honesty: "illustrative" as HonestyKind },
  { name: "Knowledge library", owner: "Intelligence Worker", connected: "Intelligence Worker", sensitivity: "Internal", assistant: "Critic + gate", honesty: "illustrative" as HonestyKind },
];

export const TABS: { id: CockpitTab; label: string }[] = [
  { id: "intelligence", label: "Intelligence" },
  { id: "observability", label: "Observability" },
  { id: "train", label: "Train" },
  { id: "sources", label: "Sources" },
  { id: "connections", label: "Connections" },
  { id: "channels", label: "Claude & Slack" },
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
  name: "Company intelligence",
  purpose: "Shared memory of what workers accomplished — property facts and intent clusters, not a separate CRM.",
  rings: "Each ring is a month of captured outcomes. Outer rings are more recent.",
};

export const SYSTEM_DETAIL: Record<SystemId, {
  purpose: string;
  allowed: string[];
  approval: string[];
  blocked: string[];
}> = {
  properties: {
    purpose: "Property, unit, and spend figures from the existing finance cockpit.",
    allowed: ["Read income, spend, and risk the operator can already see"],
    approval: [],
    blocked: ["Changing invoices or paying vendors"],
  },
  "investor-app": {
    purpose: "Investor attention already captured as intent signals.",
    allowed: ["Read and cluster repeat views"],
    approval: ["Flag a cluster for a person"],
    blocked: ["Email or message an investor"],
  },
  knowledge: {
    purpose: "Documents attached to the workers.",
    allowed: ["Grounded retrieval"],
    approval: [],
    blocked: ["Answering beyond the attached sources"],
  },
  chat: {
    purpose: "Operator chat with critic + gate.",
    allowed: ["Ask about figures or research the worker already knows"],
    approval: ["Anything that would leave the product"],
    blocked: ["Autonomous outbound contact"],
  },
};

export const WORKER_IDS: WorkerId[] = ["property-insights", "intent-intelligence"];

export function isWorkerId(value: string): value is WorkerId {
  return WORKER_IDS.includes(value as WorkerId);
}

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
