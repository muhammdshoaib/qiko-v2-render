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
    role: "Per-investor portfolio insights",
    purpose: "Joseph Mews is the property advisor. For each advised investor, read their portfolio and write grounded insight cards into their app — without contacting anyone, advising a trade, or moving money.",
    responsibilities: [
      "Inspect each advised investor’s holdings",
      "Write that investor a grounded card in the app",
      "Count insight types across clients for the operator",
    ],
    reads: [
      { title: "Investor portfolios", detail: "Each advised investor’s holdings. The worker inspects them to ground that investor’s cards." },
      { title: "Investor app", detail: "Where each client already sees their own card." },
      { title: "Knowledge library", detail: "Uploaded files when a property worker is linked." },
    ],
    writes: [
      { title: "Company intelligence", detail: "Portfolio-insight counts and concentration patterns become part of the shared record." },
    ],
    tools: [
      { name: "Read client portfolios", mode: "allowed" },
      { name: "Write a per-investor insight card", mode: "allowed" },
      { name: "Contact an investor, advise a trade, or pay a vendor", mode: "blocked" },
    ],
    hardWalls: [
      "Cannot move money or edit invoices.",
      "Does not contact investors or advise a buy or sell.",
    ],
    runs: [
      { id: "p1", time: "08:15", result: "3,104 portfolios received insights. 412 concentration cards written." },
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
      "Research answers stay inside attached documents.",
    ],
    runs: [
      { id: "i1", time: "09:40", result: "Repeat views on Lombe House flagged as intent." },
    ],
    decisions: 7,
  },
};

export const SYSTEMS: Record<SystemId, { name: string; subtitle: string }> = {
  properties: { name: "Properties", subtitle: "Client portfolio insights" },
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
    example: "412 concentration cards counted on the shared record.",
  },
  {
    id: "intent-record",
    from: "intent-intelligence",
    to: "record",
    kind: "handoff",
    label: "Intent facts",
    rule: "Flagged attention clusters become company intelligence.",
    example: "Lombe House intent recorded.",
  },
  {
    id: "property-properties",
    from: "property-insights",
    to: "properties",
    kind: "read",
    label: "Reads client portfolios",
    rule: "May read holdings each advised investor already owns.",
    example: "412 concentration cards — 3+ holdings in one city.",
  },
  {
    id: "property-knowledge",
    from: "property-insights",
    to: "knowledge",
    kind: "read",
    label: "Reads portfolio files",
    rule: "Uses uploaded portfolio documents when present.",
    example: "Holdings file used to ground a concentration card.",
  },
  {
    id: "property-chat",
    from: "property-insights",
    to: "chat",
    kind: "read",
    label: "Grounded answers",
    rule: "Chat stays behind critic + gate.",
    example: "Operator asked how many clients received a concentration card.",
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
  { id: "ev-risk", title: "412 concentration cards written", detail: "412 of 4,180 advised investors received a concentration card in their app.", at: "08:15", filter: "completed", edgeId: "property-record", focus: "property-insights" },
  { id: "ev-intent", title: "Lombe House intent captured", detail: "Lombe House / Derby repeat views flagged as interest.", at: "09:40", filter: "completed", edgeId: "intent-record", focus: "intent-intelligence" },
  { id: "ev-income", title: "Portfolio insight", detail: "Concentration card written from holdings.", at: "Mon 11:02", filter: "allowed", edgeId: "property-properties", focus: "properties" },
  { id: "ev-pay-block", title: "Advice and payment blocked", detail: "Property Insights cannot contact an investor, advise a trade, or pay a vendor.", at: "08:16", filter: "blocked", edgeId: "property-properties", focus: "property-insights" },
  { id: "ev-contact-block", title: "Investor email blocked", detail: "The Intelligence Worker cannot contact an investor.", at: "09:41", filter: "blocked", edgeId: "intent-chat", focus: "intent-intelligence" },
];

export const SOURCES = [
  { name: "Portfolio documents", owner: "Property Insights", connected: "Property Insights", sensitivity: "Commercial", assistant: "Grounded only", honesty: "illustrative" as HonestyKind },
  { name: "Investor portfolios", owner: "Advised clients", connected: "Property Insights", sensitivity: "Client holdings", assistant: "Yes, scoped", honesty: "illustrative" as HonestyKind },
  { name: "Investor activity", owner: "Intent paths", connected: "Intelligence Worker", sensitivity: "Behavioural", assistant: "Yes, scoped", honesty: "illustrative" as HonestyKind },
  { name: "Knowledge library", owner: "Intelligence Worker", connected: "Intelligence Worker", sensitivity: "Internal", assistant: "Critic + gate", honesty: "illustrative" as HonestyKind },
];

export const TABS: { id: CockpitTab; label: string }[] = [
  { id: "intelligence", label: "Pulse" },
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
  purpose: "Shared memory of what workers accomplished — per-investor portfolio insights and intent clusters, not a separate CRM.",
  rings: "Each ring is a month of captured outcomes. Outer rings are more recent.",
};

export const SYSTEM_DETAIL: Record<SystemId, {
  purpose: string;
  allowed: string[];
  approval: string[];
  blocked: string[];
}> = {
  properties: {
    purpose: "Joseph Mews advises these investors. Property Insights reads each client’s portfolio and writes grounded cards into their app. Pulse counts that work across ~4,000 clients.",
    allowed: ["Read each advised investor’s holdings", "Write a per-investor insight card"],
    approval: [],
    blocked: ["Contacting an investor", "Advising a buy or sell", "Changing invoices or paying vendors"],
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
