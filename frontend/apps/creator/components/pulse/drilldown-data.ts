import type { HonestyKind, WorkerId } from "@/components/intelligence-layer/model";
import type { BlockId } from "./route";

export type DetailKind = "conversation" | "learning" | "outcome" | "source" | "segment";

export type ChatTurn = {
  role: "in" | "out";
  speaker: string;
  text: string;
  at: string;
  captured?: string[];
};

export type Conversation = {
  id: string;
  kind: "conversation";
  who: string;
  from: string;
  channel: string;
  source: string;
  stage: string;
  stageTone: "good" | "warn" | "blue" | "";
  learned: string;
  last: string;
  honesty: HonestyKind;
  chat: ChatTurn[];
  captured: string[];
  insight: string;
  next: string;
  handoff?: { label: string; note: string };
  worker: WorkerId;
  block: BlockId;
};

export type Learning = {
  id: string;
  kind: "learning";
  title: string;
  evidence: string;
  state: "observed" | "pattern" | "proposed" | "rule";
  honesty: HonestyKind;
  worker: WorkerId;
  block: BlockId;
  needsApproval?: boolean;
};

export type Outcome = {
  id: string;
  kind: "outcome";
  title: string;
  from: string;
  summary: string;
  status: "recorded" | "awaiting" | "held";
  when: string;
  honesty: HonestyKind;
  worker: WorkerId;
  block: BlockId;
  sentTo: string[];
};

export type KnowledgeSource = {
  id: string;
  kind: "source";
  name: string;
  role: string;
  detail: string;
  honesty: HonestyKind;
};

export type Segment = {
  id: string;
  kind: "segment";
  name: string;
  countLabel: string;
  summary: string;
  signal: string;
};

export type SnapshotItem = {
  id: string;
  label: string;
  value: string;
  hint: string;
  opens: "segments" | "review" | "worker" | "sources" | "record";
};

export type CaptureItem = {
  id: string;
  title: string;
  evidence: string;
  at: string;
  chip: string;
  tone: "good" | "warn" | "blue" | "";
  detail?: string;
};

export type Accumulation = {
  month: string;
  note: string;
};

export type BlockContent = {
  id: BlockId;
  name: string;
  eyebrow: string;
  summary: string;
  snapshot: SnapshotItem[];
  segments: Segment[];
  sources: KnowledgeSource[];
  workers: WorkerId[];
  captures: CaptureItem[];
  takeaways: string[];
  accumulation: Accumulation[];
  conversations: Conversation[];
  learnings: Learning[];
  outcomes: Outcome[];
};

const INVESTOR_CONVOS: Conversation[] = [
  {
    id: "c-referral",
    kind: "conversation",
    who: "Referral sample pack",
    from: "Labelled past referrals",
    channel: "Grounded chat",
    source: "Knowledge library",
    stage: "Insight ready",
    stageTone: "warn",
    learned: "9 of 14 labelled referrals reached a person. Portal-only sessions in the same pack did so about 3 times in 10.",
    last: "Today, 10:12",
    honesty: "illustrative",
    worker: "intent-intelligence",
    block: "investors",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "In this sample pack, do referred investors behave differently from portal-only views?",
        at: "10:08",
      },
      {
        role: "out",
        speaker: "Intelligence Worker",
        text: "In the labelled sample, 9 of 14 referrals reached a person. Portal-only views in the same pack reached review about 3 times in 10. This is a sample count, not a live conversion rate.",
        at: "10:12",
        captured: ["9 of 14 referrals", "labelled sample", "not a live conversion rate"],
      },
    ],
    captured: ["14 labelled referrals", "9 reached a person", "Sample only — no live conversion"],
    insight: "The worker found a useful pattern in existing labelled evidence. A person still decides whether to write a recommendation.",
    next: "Explore, approve, or reject the referral-programme brief. Approving writes it to company intelligence. No investor is contacted.",
    handoff: {
      label: "No outbound contact",
      note: "Pulse will not send WhatsApp or email, and will not create a CRM deal. The output is a company-intelligence note.",
    },
  },
  {
    id: "c-lombay",
    kind: "conversation",
    who: "Lombay House cluster",
    from: "Investor app · repeat views",
    channel: "Grounded chat",
    source: "Investor app",
    stage: "Needs review",
    stageTone: "warn",
    learned: "Same development watched several times in one session. No investor was contacted.",
    last: "Today, 09:40",
    honesty: "illustrative",
    worker: "intent-intelligence",
    block: "investors",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "What's the next step on Lombay House?",
        at: "09:38",
      },
      {
        role: "out",
        speaker: "Intelligence Worker",
        text: "Repeat views clustered on Lombay House / Derby. A leadership review is recommended. No investor was contacted.",
        at: "09:40",
        captured: ["Lombay House / Derby", "repeat views", "no outreach"],
      },
    ],
    captured: ["Repeat views on Lombay House", "Development: Derby", "No outbound contact"],
    insight: "Attention is already in the investor app. The worker clustered it; a person decides whether to follow up.",
    next: "Approve or hold the review. Approving writes the cluster to company intelligence.",
    handoff: {
      label: "CRM hand-off is not live",
      note: "This prototype does not create a CRM record. The next step stays a human review inside Pulse.",
    },
  },
  {
    id: "c-listing",
    kind: "conversation",
    who: "Listing research",
    from: "Knowledge library",
    channel: "Grounded chat",
    source: "Knowledge library",
    stage: "Answered",
    stageTone: "good",
    learned: "Answer stayed inside attached documents. Critic + gate held.",
    last: "Yesterday, 16:22",
    honesty: "illustrative",
    worker: "intent-intelligence",
    block: "investors",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "What does the attached pack say about the Derby listing?",
        at: "16:18",
      },
      {
        role: "out",
        speaker: "Intelligence Worker",
        text: "The attached research describes the Derby listing and recent viewing activity. I cannot add facts that are not in the library, and I cannot email an investor.",
        at: "16:22",
        captured: ["Derby listing", "attached research only"],
      },
    ],
    captured: ["Question scoped to attached knowledge", "No outbound email"],
    insight: "Research answers stay behind the critic + gate. The library is the source, not the open web.",
    next: "Use the answer internally. Contacting anyone stays blocked.",
  },
  {
    id: "c-quiet",
    kind: "conversation",
    who: "Quiet developments",
    from: "Investor app · 7-day gap",
    channel: "Recorded note",
    source: "Investor app",
    stage: "Recorded",
    stageTone: "blue",
    learned: "Two listings had no new intent in 7 days.",
    last: "Yesterday, 16:22",
    honesty: "illustrative",
    worker: "intent-intelligence",
    block: "investors",
    chat: [
      {
        role: "out",
        speaker: "Intelligence Worker",
        text: "Two listings had no new investor-app views in 7 days. Written to the activity feed. No investor email was sent.",
        at: "16:22",
        captured: ["7-day quiet", "two listings"],
      },
    ],
    captured: ["Quiet listings", "No outreach"],
    insight: "Absence of attention is also knowledge. It sits on the Investors block, not in a CRM.",
    next: "A person can look at those listings. The worker will not chase anyone.",
  },
];

const PROPERTY_CONVOS: Conversation[] = [
  {
    id: "c-spend",
    kind: "conversation",
    who: "High-cost unit",
    from: "Finance cockpit",
    channel: "Grounded chat",
    source: "Studio finance cockpit",
    stage: "Recorded",
    stageTone: "good",
    learned: "Labelled sample: £4,200 this period. Property Insights cannot change the invoice or pay the vendor.",
    last: "Today, 08:15",
    honesty: "illustrative",
    worker: "property-insights",
    block: "properties",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "How much did the high-cost unit spend this period?",
        at: "08:12",
      },
      {
        role: "out",
        speaker: "Property Insights",
        text: "Labelled sample: £4,200 this period. Property Insights cannot change the invoice or pay the vendor.",
        at: "08:15",
        captured: ["£4,200 this period", "cannot pay vendor"],
      },
    ],
    captured: ["Spend figure (sample)", "Hard wall: no payment"],
    insight: "The worker can summarise spend the operator can already see. It cannot move money.",
    next: "Read the risk note. Any payment stays with a person.",
  },
  {
    id: "c-income",
    kind: "conversation",
    who: "Portfolio income",
    from: "Property records",
    channel: "Recorded note",
    source: "Studio finance cockpit",
    stage: "Recorded",
    stageTone: "blue",
    learned: "Portfolio income held flat week-on-week.",
    last: "Mon, 11:02",
    honesty: "illustrative",
    worker: "property-insights",
    block: "properties",
    chat: [
      {
        role: "out",
        speaker: "Property Insights",
        text: "Portfolio income held flat week-on-week. Written as an operator-readable snapshot, not a new report.",
        at: "11:02",
        captured: ["income held flat"],
      },
    ],
    captured: ["Income snapshot"],
    insight: "Existing cockpit figures, restated so they can sit on the Properties block.",
    next: "No action required unless spend drifts again.",
  },
];

export const BLOCKS: Record<BlockId, BlockContent> = {
  investors: {
    id: "investors",
    name: "Investors",
    eyebrow: "Knowledge block · 1 worker",
    summary: "Repeat buyers, portfolio owners, and the attention they already show in the investor app. This is not a CRM — it is the knowledge the Intelligence Worker may read and record.",
    snapshot: [
      { id: "engagement", label: "App engagement", value: "Repeat views", hint: "Where data exists: clustered investor-app sessions, not a headcount.", opens: "segments" },
      { id: "segments", label: "Segments", value: "2 groups", hint: "Repeat attention vs quiet listings.", opens: "segments" },
      { id: "review", label: "Needs a person", value: "1 recommendation", hint: "Referral programme brief awaiting a decision. Sample evidence only.", opens: "review" },
      { id: "worker", label: "Contributing worker", value: "Intelligence", hint: "Intent signals and grounded research.", opens: "worker" },
      { id: "record", label: "On the record", value: "7 notes", hint: "Illustrative count of recorded decisions.", opens: "record" },
    ],
    segments: [
      {
        id: "repeat",
        kind: "segment",
        name: "Repeat attention",
        countLabel: "1 cluster",
        summary: "Same development watched several times in one session.",
        signal: "Lombay House / Derby — flagged for a person.",
      },
      {
        id: "quiet",
        kind: "segment",
        name: "Quiet listings",
        countLabel: "2 listings",
        summary: "No new investor-app views in 7 days.",
        signal: "Absence of attention is also written to this block.",
      },
      {
        id: "referrals",
        kind: "segment",
        name: "Referred arrivals",
        countLabel: "14 in sample",
        summary: "Labelled past referrals in the sample pack — not live traffic.",
        signal: "9 reached a person vs about 3 in 10 portal-only sessions.",
      },
    ],
    sources: [
      { id: "src-app", kind: "source", name: "Investor app", role: "Intent signals", detail: "Existing viewing and calculator activity, when that path is linked. The worker may cluster it. It may not email an investor.", honesty: "illustrative" },
      { id: "src-lib", kind: "source", name: "Knowledge library", role: "Uploaded sources", detail: "Documents attached to the Intelligence Worker. Answers stay inside those files.", honesty: "connected" },
      { id: "src-chat", kind: "source", name: "Grounded chat", role: "Critic + gate", detail: "Operator questions about research or intent. Outbound contact stays blocked.", honesty: "connected" },
      { id: "src-crm", kind: "source", name: "Client CRM", role: "Not connected", detail: "Ed's HTML shows a CRM hand-off. This prototype does not create CRM records. A hand-off would stay a planned next step.", honesty: "planned" },
    ],
    workers: ["intent-intelligence"],
    captures: [
      { id: "referrals", title: "Referral sample reached review more often", evidence: "9 of 14 labelled referrals reached a person. Portal-only sessions in the same pack did so about 3 times in 10.", at: "Today, 10:12", chip: "Insight ready", tone: "warn", detail: "c-referral" },
      { id: "repeat", title: "Repeat views on Lombay House", evidence: "Same development watched several times in one session.", at: "Today, 09:40", chip: "Needs review", tone: "warn", detail: "c-lombay" },
      { id: "quiet", title: "Quiet developments", evidence: "Two listings had no new intent in 7 days.", at: "Yesterday, 16:22", chip: "Recorded", tone: "blue", detail: "c-quiet" },
      { id: "signal", title: "Intent signal captured", evidence: "Written to the activity feed. No investor email was sent.", at: "Yesterday, 16:22", chip: "On the record", tone: "good", detail: "o-signal" },
    ],
    takeaways: [
      "Investor knowledge here is attention and research — what people looked at, and what attached documents can safely say.",
      "The Intelligence Worker can flag a cluster. Contacting anyone stays a hard wall.",
      "Approving the referral brief writes that decision to company intelligence. Rejecting it keeps the insight and writes nothing.",
    ],
    accumulation: [
      { month: "Jul", note: "Intent paths described. No referral pattern on the record." },
      { month: "Aug", note: "Grounded chat answers stay behind the critic + gate." },
      { month: "Sep", note: "Quiet-listing notes start landing on this block." },
      { month: "Oct", note: "Labelled referral sample surfaced. A person still decides whether to write the brief." },
    ],
    conversations: INVESTOR_CONVOS,
    learnings: [
      { id: "l-referral", kind: "learning", title: "Referred arrivals in the labelled sample reached review more often", evidence: "14 labelled past referrals; 9 reached a person. This is a sample count, not a live conversion rate.", state: "proposed", honesty: "illustrative", worker: "intent-intelligence", block: "investors" },
      { id: "l-review", kind: "learning", title: "Repeat views on one listing should be flagged for a person", evidence: "Lombay House / Derby is the worked example. The worker clusters; it does not outreach.", state: "proposed", honesty: "illustrative", worker: "intent-intelligence", block: "investors", needsApproval: true },
      { id: "l-wall", kind: "learning", title: "No outbound investor email", evidence: "Hard wall on the Intelligence Worker. Recorded every time a cluster is written.", state: "rule", honesty: "connected", worker: "intent-intelligence", block: "investors" },
      { id: "l-gate", kind: "learning", title: "Research answers stay behind the critic + gate", evidence: "Listing questions are answered only from the knowledge library.", state: "rule", honesty: "connected", worker: "intent-intelligence", block: "investors" },
      { id: "l-quiet", kind: "learning", title: "A 7-day gap in views is worth recording", evidence: "Two listings in the sample week. Too few to make a company rule.", state: "pattern", honesty: "illustrative", worker: "intent-intelligence", block: "investors" },
    ],
    outcomes: [
      { id: "o-referral", kind: "outcome", title: "Referral programme recommendation", from: "Labelled sample of past referrals", summary: "Write a recommendation to company intelligence: thank repeat investors who refer, then a person decides any outreach. Sample counts only — not a conversion or revenue forecast.", status: "awaiting", when: "Today, 10:12", honesty: "illustrative", worker: "intent-intelligence", block: "investors", sentTo: ["Investors block (after approval)", "Company intelligence (after approval)"] },
      { id: "o-lombay", kind: "outcome", title: "Lombay cluster flagged", from: "Repeat views in the investor app", summary: "The Intelligence Worker recorded a cluster and asked for a human look. Nothing was sent outbound.", status: "awaiting", when: "Today, 09:40", honesty: "illustrative", worker: "intent-intelligence", block: "investors", sentTo: ["Company intelligence (after approval)"] },
      { id: "o-signal", kind: "outcome", title: "Intent signal captured", from: "Investor-app views", summary: "A cluster of views was written to the activity feed as a sample of existing intent-signal capability.", status: "recorded", when: "Yesterday, 16:22", honesty: "illustrative", worker: "intent-intelligence", block: "investors", sentTo: ["Investors block", "Activity feed"] },
    ],
  },
  properties: {
    id: "properties",
    name: "Properties",
    eyebrow: "Knowledge block · 1 worker",
    summary: "Income, spend, and risk the operator can already see in the finance cockpit. Property Insights writes notes here — it does not pay vendors or invent a second ledger.",
    snapshot: [
      { id: "known", label: "Known figures", value: "Cockpit", hint: "Existing property and spend records, not a new database.", opens: "sources" },
      { id: "insights", label: "Insights", value: "2 notes", hint: "Expenditure drift and an income snapshot.", opens: "segments" },
      { id: "review", label: "Payments", value: "Blocked", hint: "The worker cannot move money.", opens: "review" },
      { id: "worker", label: "Contributing worker", value: "Property Insights", hint: "Reads the cockpit, writes operator notes.", opens: "worker" },
      { id: "record", label: "On the record", value: "11 notes", hint: "Illustrative count of recorded decisions.", opens: "record" },
    ],
    segments: [
      {
        id: "drift",
        kind: "segment",
        name: "Expenditure drift",
        countLabel: "1 unit",
        summary: "One unit is running above the recent spend band.",
        signal: "Sample spend this period: £4,200. Invoice unchanged.",
      },
      {
        id: "income",
        kind: "segment",
        name: "Income held",
        countLabel: "Portfolio",
        summary: "Portfolio income held flat week-on-week.",
        signal: "A snapshot, not a forecast.",
      },
    ],
    sources: [
      { id: "src-fin", kind: "source", name: "Studio finance cockpit", role: "Property ledger", detail: "Income, unit, and vendor views the operator can already open. This is the source of truth for figures.", honesty: "connected" },
      { id: "src-up", kind: "source", name: "Finance uploads", role: "Knowledge library", detail: "Spreadsheets attached to Property Insights, used only when present.", honesty: "illustrative" },
      { id: "src-chat", kind: "source", name: "Grounded chat", role: "Critic + gate", detail: "Ask for a spend or income summary. Paying a vendor stays blocked.", honesty: "connected" },
    ],
    workers: ["property-insights"],
    captures: [
      { id: "drift", title: "Expenditure drift", evidence: "One unit is running above the recent spend band.", at: "Today, 08:15", chip: "Risk note", tone: "warn", detail: "c-spend" },
      { id: "income", title: "Income snapshot", evidence: "Portfolio income held flat week-on-week.", at: "Mon, 11:02", chip: "Recorded", tone: "blue", detail: "c-income" },
      { id: "note", title: "Risk note written", evidence: "Operator-readable summary, not an automated vendor payment.", at: "Today, 08:15", chip: "On the record", tone: "good", detail: "o-risk" },
    ],
    takeaways: [
      "Properties is the finance view of company intelligence — income, cost, and risk.",
      "Property Insights can draft a note. It cannot edit invoices or pay a vendor.",
      "The same block structure as Investors: sources, one worker, captured notes, a growing record.",
    ],
    accumulation: [
      { month: "Jul", note: "Finance cockpit figures available to the worker." },
      { month: "Aug", note: "Income snapshots start landing on this block." },
      { month: "Sep", note: "First drift notes written as operator-readable summaries." },
      { month: "Oct", note: "£4,200 sample spend recorded. Payment remains blocked." },
    ],
    conversations: PROPERTY_CONVOS,
    learnings: [
      { id: "l-note", kind: "learning", title: "Risk notes are summaries, not payments", evidence: "The drift note names the unit and the sample spend. The invoice is untouched.", state: "rule", honesty: "connected", worker: "property-insights", block: "properties" },
      { id: "l-pay", kind: "learning", title: "Cannot move money or edit invoices", evidence: "Hard wall. Asked every time a spend figure is shared.", state: "rule", honesty: "connected", worker: "property-insights", block: "properties" },
    ],
    outcomes: [
      { id: "o-risk", kind: "outcome", title: "Property risk note published", from: "Finance cockpit spend band", summary: "Property Insights summarised expenditure drift on a high-cost unit. Sample from the finance cockpit capability.", status: "recorded", when: "Today, 08:15", honesty: "illustrative", worker: "property-insights", block: "properties", sentTo: ["Properties block", "Company intelligence"] },
    ],
  },
};

export const ALL_CONVERSATIONS = [...INVESTOR_CONVOS, ...PROPERTY_CONVOS];
export const ALL_LEARNINGS = [...BLOCKS.investors.learnings, ...BLOCKS.properties.learnings];
export const ALL_OUTCOMES = [...BLOCKS.investors.outcomes, ...BLOCKS.properties.outcomes];
export const ALL_SOURCES = [...BLOCKS.investors.sources, ...BLOCKS.properties.sources];
export const ALL_SEGMENTS = [...BLOCKS.investors.segments, ...BLOCKS.properties.segments];

export function findDetail(id: string | null) {
  if (!id) return null;
  return (
    ALL_CONVERSATIONS.find((item) => item.id === id)
    ?? ALL_LEARNINGS.find((item) => item.id === id)
    ?? ALL_OUTCOMES.find((item) => item.id === id)
    ?? ALL_SOURCES.find((item) => item.id === id)
    ?? ALL_SEGMENTS.find((item) => item.id === id)
    ?? null
  );
}

export const LEARNING_LABEL: Record<Learning["state"], { label: string; tone: "good" | "warn" | "blue" | "" }> = {
  observed: { label: "Observed", tone: "" },
  pattern: { label: "Pattern", tone: "blue" },
  proposed: { label: "Awaiting approval", tone: "warn" },
  rule: { label: "In force", tone: "good" },
};

export const SHEET_CLASS =
  "fixed inset-y-0 right-0 top-0 left-auto flex h-full max-h-none w-full max-w-[min(540px,100%)] translate-x-0 translate-y-0 flex-col gap-0 overflow-y-auto rounded-none border-y-0 border-l border-white/10 bg-popover text-popover-foreground p-0 shadow-[-20px_0_50px_-20px_rgba(0,0,0,.65)] sm:max-w-[min(540px,100%)] data-[state=open]:zoom-in-100";
