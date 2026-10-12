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
  opens: "segments" | "review" | "worker" | "sources" | "record" | "activity";
  honesty?: HonestyKind;
  detail?: string;
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
    who: "Lombe House reachout",
    from: "Lombe House intent signal",
    channel: "Grounded chat",
    source: "Investor app",
    stage: "Insight ready",
    stageTone: "warn",
    learned: "Repeat views on Lombe House were treated as intent. From that intelligence, a referral reachout is recommended.",
    last: "Today, 10:12",
    honesty: "illustrative",
    worker: "intent-intelligence",
    block: "investors",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "This investor has viewed Lombe House several times. What should we do?",
        at: "10:08",
      },
      {
        role: "out",
        speaker: "Intelligence Worker",
        text: "Repeat views on Lombe House are an intent signal. Recommend a referral reachout. A person still decides. Pulse will not send WhatsApp or email.",
        at: "10:12",
        captured: ["Lombe House", "intent signal", "referral reachout", "Pulse will not send WhatsApp or email"],
      },
    ],
    captured: ["Lombe House intent", "Referral reachout recommended", "No outbound contact"],
    insight: "The worker showed the Lombe House intent first, then suggested the next action. A person still decides whether to write the recommendation.",
    next: "Explore, approve, or reject the referral reachout brief. Approving writes it to company intelligence. No investor is contacted.",
    handoff: {
      label: "No outbound contact",
      note: "Pulse will not send WhatsApp or email, and will not create a CRM deal. The output is a company-intelligence note.",
    },
  },
  {
    id: "c-lombay",
    kind: "conversation",
    who: "Lombe House intent",
    from: "Investor app · repeat views",
    channel: "Grounded chat",
    source: "Investor app",
    stage: "Recorded",
    stageTone: "good",
    learned: "Same investor opened Lombe House several times. The intent worker flagged interest. No investor was contacted.",
    last: "Today, 09:40",
    honesty: "illustrative",
    worker: "intent-intelligence",
    block: "investors",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "What does this investor's activity on Lombe House mean?",
        at: "09:38",
      },
      {
        role: "out",
        speaker: "Intelligence Worker",
        text: "Repeat views on Lombe House / Derby meet the intent threshold. This investor is showing interest. Labelled sample — not the live admin feed. No investor was contacted.",
        at: "09:40",
        captured: ["Lombe House / Derby", "intent threshold", "showing interest", "no outreach"],
      },
    ],
    captured: ["Repeat views on Lombe House", "Development: Derby", "Intent signal captured", "No outbound contact"],
    insight: "This is the intelligence the intent worker produces for Joseph Mews admin. Pulse shows it. The referral reachout is the recommended next action, not a second unrelated plot.",
    next: "The referral reachout recommendation is waiting on a person. This intent stays on Investors either way.",
    handoff: {
      label: "CRM hand-off is not live",
      note: "This prototype does not create a CRM record. Recommending a reachout does not send one.",
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
    learned: "Answer stayed inside attached documents.",
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
    insight: "Research answers stay inside attached documents. The library is the source, not the open web.",
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
    id: "c-insights",
    kind: "conversation",
    who: "Portfolio insights written",
    from: "Each advised investor’s holdings",
    channel: "Recorded note",
    source: "Investor portfolios",
    stage: "Recorded",
    stageTone: "good",
    learned: "The worker read each advised investor’s portfolio and wrote grounded cards into their app. 3,104 of 4,180 had enough holdings to ground at least one insight this month.",
    last: "Today, 07:40",
    honesty: "illustrative",
    worker: "property-insights",
    block: "properties",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "What did Property Insights actually do this month? These are our clients' portfolios, not our stock.",
        at: "07:36",
      },
      {
        role: "out",
        speaker: "Property Insights",
        text: "Joseph Mews advises 4,180 investors in the labelled sample. I read each portfolio and wrote cards into that investor’s app — concentration, regional performance, income, or pipeline, only where the holdings support it. 3,104 received at least one card. I did not contact anyone, and I did not tell anyone to buy or sell.",
        at: "07:40",
        captured: ["read each portfolio", "wrote cards into that investor’s app", "3,104 received at least one card", "did not tell anyone to buy or sell"],
      },
    ],
    captured: ["4,180 advised investors", "3,104 with a grounded insight", "Per-investor cards in the app"],
    insight: "This worker is insight generation for Joseph Mews’ clients. Pulse shows how many portfolios were read and which insight types landed — not Joseph Mews’ own property stock.",
    next: "Open a category to see the pattern across clients. Contacting an investor stays blocked.",
    handoff: {
      label: "Does not contact investors",
      note: "Each client may already see their own card in the app. Pulse will not message them. The worker does not give buy/sell advice and cannot move money.",
    },
  },
  {
    id: "c-concentration",
    kind: "conversation",
    who: "Concentration cards",
    from: "Each advised investor’s holdings",
    channel: "Grounded chat",
    source: "Investor portfolios",
    stage: "Recorded",
    stageTone: "good",
    learned: "412 advised investors received a concentration card: three or more holdings in one city. London is the largest cluster. Each card was written for that investor, not as Joseph Mews stock.",
    last: "Today, 08:15",
    honesty: "illustrative",
    worker: "property-insights",
    block: "properties",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "How many of our clients have an undiversified portfolio?",
        at: "08:12",
      },
      {
        role: "out",
        speaker: "Property Insights",
        text: "412 of 4,180 advised investors received a concentration card — three or more holdings in one city. London is the largest cluster. Example shape of one card: “You have 3 properties in London; this portfolio is not diverse.” That line is written to that investor’s app. Pulse counts how many clients got that kind of insight.",
        at: "08:15",
        captured: ["412 of 4,180 advised investors", "concentration card", "You have 3 properties in London"],
      },
    ],
    captured: ["412 concentration cards", "London largest cluster", "Written per investor, counted here"],
    insight: "The worker checks each client’s portfolio, then builds the insight. The operator sees the count across clients. Nobody is contacted.",
    next: "Use the pattern internally. Contacting anyone stays blocked.",
    handoff: {
      label: "Does not contact investors",
      note: "The concentration card already sits in the investor app. Pulse will not message them, and the worker will not advise a purchase or sale.",
    },
  },
  {
    id: "c-holdings",
    kind: "conversation",
    who: "Client holdings read",
    from: "Advised investors’ portfolios",
    channel: "Recorded note",
    source: "Investor portfolios",
    stage: "Recorded",
    stageTone: "blue",
    learned: "2,140 holdings belong to advised investors. They are the input the worker reads. They are not Joseph Mews stock.",
    last: "Yesterday, 15:10",
    honesty: "illustrative",
    worker: "property-insights",
    block: "properties",
    chat: [
      {
        role: "in",
        speaker: "Operator",
        text: "What is the worker actually reading?",
        at: "15:06",
      },
      {
        role: "out",
        speaker: "Property Insights",
        text: "2,140 holdings across 4,180 advised investors in the labelled sample. I read each client’s portfolio to ground their cards. Joseph Mews does not own these units. I cannot edit a holding or move money.",
        at: "15:10",
        captured: ["2,140 holdings", "advised investors", "Joseph Mews does not own these units"],
      },
    ],
    captured: ["2,140 client holdings", "Input to insight generation", "Not Joseph Mews stock"],
    insight: "Holdings are what the worker inspects. Insights are what it writes. Pulse must not treat client assets as company inventory.",
    next: "Any change to a holding stays with a person. The worker only writes observations.",
  },
  {
    id: "c-spend",
    kind: "conversation",
    who: "Advice and contact walls",
    from: "Guardrails",
    channel: "Recorded note",
    source: "Worker restrictions",
    stage: "Recorded",
    stageTone: "blue",
    learned: "Property Insights observes. It does not contact the investor, advise a buy or sell, or move money.",
    last: "Mon, 11:02",
    honesty: "connected",
    worker: "property-insights",
    block: "properties",
    chat: [
      {
        role: "out",
        speaker: "Property Insights",
        text: "Portfolio insights are observations for each advised investor. I cannot email them, I cannot tell them to buy or sell, and I cannot move money.",
        at: "11:02",
        captured: ["cannot email them", "cannot tell them to buy or sell", "cannot move money"],
      },
    ],
    captured: ["No outbound contact", "No buy/sell advice", "No payments"],
    insight: "The worker’s job stops at the grounded card. Joseph Mews advisors still own any conversation.",
    next: "Any outreach stays a human decision on Investors. This worker will not send it.",
  },
];

export const BLOCKS: Record<BlockId, BlockContent> = {
  investors: {
    id: "investors",
    name: "Investors",
    eyebrow: "Knowledge block",
    summary: "The labelled register of ~4,000 investors: who is using the app, who is showing intent, and which reachouts still need a person — not a CRM.",
    snapshot: [
      { id: "total", label: "Investors on the book", value: "4,180", hint: "Illustrative register — not a live CRM count.", opens: "segments", honesty: "illustrative" },
      { id: "active", label: "Using the app", value: "612", hint: "Illustrative · last 30 days in the investor app.", opens: "activity", honesty: "illustrative" },
      { id: "intent", label: "High-intent", value: "28", hint: "Illustrative · repeat views or calculator. Lombe House is the worked example.", opens: "segments", honesty: "illustrative", detail: "repeat" },
      { id: "progress", label: "Reachouts awaiting", value: "1 of 9", hint: "Labelled · 9 recorded this quarter; 1 still needs a person (Lombe House).", opens: "review", honesty: "illustrative" },
    ],
    segments: [
      {
        id: "repeat",
        kind: "segment",
        name: "Repeat attention",
        countLabel: "28 high-intent",
        summary: "Investors whose activity met the intent threshold. Lombe House is the worked example.",
        signal: "One of 28: Lombe House / Derby — intent captured. A referral reachout is the recommended next action.",
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
        name: "Investor reachouts",
        countLabel: "9 this quarter",
        summary: "Recommended reachouts written to company intelligence. Pulse does not send them.",
        signal: "8 recorded. 1 awaiting a person (Lombe House). Hard wall: no WhatsApp, email, or CRM deal.",
      },
      {
        id: "holdings-link",
        kind: "segment",
        name: "Client portfolios",
        countLabel: "3,104 with insights",
        summary: "Property Insights reads each advised investor’s holdings and writes their cards. Those counts sit on Properties.",
        signal: "Open Properties for portfolio-insight patterns across clients. This block stays attention and reachouts.",
      },
    ],
    sources: [
      { id: "src-app", kind: "source", name: "Investor app", role: "Intent signals", detail: "Existing viewing and calculator activity, when that path is linked. The worker may cluster it. It may not email an investor.", honesty: "illustrative" },
      { id: "src-lib", kind: "source", name: "Knowledge library", role: "Uploaded sources", detail: "Documents attached to the Intelligence Worker. Answers stay inside those files.", honesty: "connected" },
      { id: "src-chat", kind: "source", name: "Grounded chat", role: "Operator questions", detail: "Operator questions about research or intent. Answers stay inside attached documents. Outbound contact stays blocked.", honesty: "connected" },
      { id: "src-crm", kind: "source", name: "Client CRM", role: "Not connected", detail: "Not connected. A hand-off would stay a planned next step — this prototype does not create CRM records.", honesty: "planned" },
    ],
    workers: ["intent-intelligence"],
    captures: [
      { id: "referrals", title: "Referral reachout recommended from Lombe House intent", evidence: "One of 28 high-intent investors. Repeat views flagged interest. A person should decide on a referral reachout.", at: "Today, 10:12", chip: "Insight ready", tone: "warn", detail: "c-referral" },
      { id: "repeat", title: "Lombe House intent captured", evidence: "Worked example from the 28 high-intent set. No outreach was sent.", at: "Today, 09:40", chip: "On the record", tone: "good", detail: "c-lombay" },
      { id: "reachouts", title: "8 reachouts already on the record", evidence: "Labelled quarter: 8 recommended reachouts were written after a person decided. Pulse sent none of them.", at: "This quarter", chip: "On the record", tone: "good", detail: "o-reachouts" },
      { id: "quiet", title: "Quiet developments", evidence: "Two listings had no new intent in 7 days.", at: "Yesterday, 16:22", chip: "Recorded", tone: "blue", detail: "c-quiet" },
      { id: "signal", title: "Intent signal captured", evidence: "Written to the activity feed. No investor email was sent.", at: "Yesterday, 16:22", chip: "On the record", tone: "good", detail: "o-signal" },
    ],
    takeaways: [
      "This block is the ~4,000-investor register: attention, intent, and reachouts — not one person's file.",
      "The Intelligence Worker can flag intent. Contacting anyone stays a hard wall.",
      "Lombe House is the worked example. The referral reachout is the recommended action from that intelligence.",
    ],
    accumulation: [
      { month: "Jul", note: "Register and intent paths described. Reachouts not yet on the record." },
      { month: "Aug", note: "Grounded chat answers stay inside attached documents." },
      { month: "Sep", note: "Quiet-listing notes and the first recorded reachouts land on this block." },
      { month: "Oct", note: "28 high-intent. Lombe House is the worked example. 1 reachout still needs a person." },
    ],
    conversations: INVESTOR_CONVOS,
    learnings: [
      { id: "l-referral", kind: "learning", title: "Lombe House intent supports a referral reachout", evidence: "Repeat views flagged interest. From that intelligence, a referral reachout is recommended. Labelled sample — not the live admin feed.", state: "observed", honesty: "illustrative", worker: "intent-intelligence", block: "investors" },
      { id: "l-review", kind: "learning", title: "Repeat views on Lombe House / Derby flagged as intent", evidence: "Same investor opened Lombe House several times. The worker clustered this; it did not outreach.", state: "observed", honesty: "illustrative", worker: "intent-intelligence", block: "investors" },
      { id: "l-wall", kind: "learning", title: "No outbound investor email", evidence: "Hard wall on the Intelligence Worker. Recorded every time a cluster is written.", state: "rule", honesty: "connected", worker: "intent-intelligence", block: "investors" },
      { id: "l-gate", kind: "learning", title: "Research answers stay inside attached documents", evidence: "Listing questions are answered only from the knowledge library.", state: "rule", honesty: "connected", worker: "intent-intelligence", block: "investors" },
      { id: "l-quiet", kind: "learning", title: "A 7-day gap in views is worth recording", evidence: "Two listings in the sample week. Too few to make a company rule.", state: "pattern", honesty: "illustrative", worker: "intent-intelligence", block: "investors" },
    ],
    outcomes: [
      { id: "o-referral", kind: "outcome", title: "Referral reachout recommendation", from: "Lombe House intent signal", summary: "Write a recommendation to company intelligence: a person should decide on a referral reachout for this Lombe House intent. Nothing will be sent automatically.", status: "awaiting", when: "Today, 10:12", honesty: "illustrative", worker: "intent-intelligence", block: "investors", sentTo: ["Investors block (after approval)", "Company intelligence (after approval)"] },
      { id: "o-lombay", kind: "outcome", title: "Lombe House intent captured", from: "Repeat views in the investor app", summary: "Worked example from the high-intent set. The Intelligence Worker recorded interest. Nothing was sent outbound.", status: "recorded", when: "Today, 09:40", honesty: "illustrative", worker: "intent-intelligence", block: "investors", sentTo: ["Investors block", "Company intelligence"] },
      { id: "o-reachouts", kind: "outcome", title: "8 reachouts already on the record", from: "Prior intent signals this quarter", summary: "Labelled sample: eight recommended reachouts were written after a person decided. Pulse sent none of them. CRM is not connected.", status: "recorded", when: "This quarter", honesty: "illustrative", worker: "intent-intelligence", block: "investors", sentTo: ["Investors block", "Company intelligence"] },
      { id: "o-signal", kind: "outcome", title: "Intent signal captured", from: "Investor-app views", summary: "A cluster of views was written to the activity feed as a sample of existing intent-signal capability.", status: "recorded", when: "Yesterday, 16:22", honesty: "illustrative", worker: "intent-intelligence", block: "investors", sentTo: ["Investors block", "Activity feed"] },
    ],
  },
  properties: {
    id: "properties",
    name: "Properties",
    eyebrow: "Knowledge block",
    summary: "Joseph Mews advises these investors. Property Insights reads each client’s portfolio and writes grounded cards into their app. Pulse counts that work across ~4,000 clients — it is not Joseph Mews’ own stock.",
    snapshot: [
      { id: "advised", label: "Advised investors", value: "4,180", hint: "Illustrative · Joseph Mews clients, not a live CRM count.", opens: "segments", honesty: "illustrative", detail: "portfolios" },
      { id: "generated", label: "Portfolios with insights", value: "3,104", hint: "Illustrative · enough holdings to ground at least one card this month.", opens: "activity", honesty: "illustrative", detail: "c-insights" },
      { id: "holdings", label: "Client holdings read", value: "2,140", hint: "Illustrative · properties those investors own. Not Joseph Mews stock.", opens: "activity", honesty: "illustrative", detail: "c-holdings" },
      { id: "insights", label: "Concentration cards", value: "412", hint: "Illustrative · clients who received a “not diverse” card.", opens: "segments", honesty: "illustrative", detail: "concentration" },
    ],
    segments: [
      {
        id: "portfolios",
        kind: "segment",
        name: "Portfolios read",
        countLabel: "3,104 of 4,180",
        summary: "The worker inspects each advised investor’s holdings, then writes up to three grounded cards into their app.",
        signal: "Empty portfolios get no invented card. Contacting the client stays blocked.",
      },
      {
        id: "concentration",
        kind: "segment",
        name: "Concentration insights",
        countLabel: "412 cards",
        summary: "Clients with three or more holdings in one city. London is the largest cluster.",
        signal: "Example card in the app: “You have 3 properties in London; this portfolio is not diverse.”",
      },
      {
        id: "holdings-seg",
        kind: "segment",
        name: "Client holdings",
        countLabel: "2,140 properties",
        summary: "What the worker reads. These units belong to advised investors, not to Joseph Mews.",
        signal: "Input to insight generation. The worker cannot edit a holding.",
      },
      {
        id: "paywall",
        kind: "segment",
        name: "Walls in force",
        countLabel: "Blocked",
        summary: "No outbound contact. No buy/sell advice. No payments.",
        signal: "Joseph Mews advisors still own any conversation with the client.",
      },
    ],
    sources: [
      { id: "src-holdings", kind: "source", name: "Investor portfolios", role: "What the worker reads", detail: "Each advised investor’s holdings. The worker inspects them to ground that investor’s cards.", honesty: "illustrative" },
      { id: "src-app-insights", kind: "source", name: "Investor app", role: "Where the cards land", detail: "Per-investor insight cards already shown to the client. Pulse counts the pattern; it does not open one file as the overview.", honesty: "illustrative" },
      { id: "src-up", kind: "source", name: "Knowledge library", role: "Uploaded sources", detail: "Documents attached to Property Insights, used only when present.", honesty: "connected" },
      { id: "src-prop-chat", kind: "source", name: "Grounded chat", role: "Operator questions", detail: "Ask how many clients received which insight type. Contacting them and advising a buy or sell stay blocked.", honesty: "connected" },
    ],
    workers: ["property-insights"],
    captures: [
      { id: "generated", title: "3,104 portfolios received insights this month", evidence: "The worker read each advised investor’s holdings and wrote grounded cards into their app. Empty portfolios got no invented card.", at: "Today, 07:40", chip: "On the record", tone: "good", detail: "c-insights" },
      { id: "concentration", title: "412 concentration cards", evidence: "Clients with 3+ holdings in one city. Example in the app: “You have 3 properties in London; this portfolio is not diverse.”", at: "Today, 08:15", chip: "On the record", tone: "good", detail: "c-concentration" },
      { id: "holdings", title: "2,140 client holdings read", evidence: "Properties those investors own. Input to insight generation — not Joseph Mews stock.", at: "Yesterday, 15:10", chip: "On the record", tone: "blue", detail: "c-holdings" },
      { id: "paywall", title: "Advice and contact walls", evidence: "No outbound email. No buy/sell advice. Cannot move money.", at: "Mon, 11:02", chip: "Recorded", tone: "blue", detail: "c-spend" },
    ],
    takeaways: [
      "Joseph Mews is the property advisor. These holdings belong to its clients.",
      "Property Insights checks each investor’s portfolio, then writes that investor a grounded card.",
      "Pulse shows the pattern across ~4,000 clients. It does not treat client assets as company stock, and it does not contact anyone.",
    ],
    accumulation: [
      { month: "Jul", note: "Advised investors’ holdings first readable by the worker." },
      { month: "Aug", note: "First per-investor cards land in the investor app." },
      { month: "Sep", note: "Concentration, regional, income, and pipeline categories counted across clients." },
      { month: "Oct", note: "3,104 portfolios with insights. 412 concentration cards. Walls still in force." },
    ],
    conversations: PROPERTY_CONVOS,
    learnings: [
      { id: "l-book", kind: "learning", title: "Read each client’s portfolio, then write their card", evidence: "4,180 advised investors in the labelled sample. 3,104 had enough holdings to ground at least one insight. Empty portfolios stay empty.", state: "rule", honesty: "illustrative", worker: "property-insights", block: "properties" },
      { id: "l-note", kind: "learning", title: "A concentration card names the city and the count — it is not advice", evidence: "412 clients. Example: “You have 3 properties in London.” It does not tell them to buy or sell.", state: "pattern", honesty: "illustrative", worker: "property-insights", block: "properties" },
      { id: "l-pay", kind: "learning", title: "Cannot contact investors, advise a trade, or move money", evidence: "Hard walls. Asked every time a portfolio card is written.", state: "rule", honesty: "connected", worker: "property-insights", block: "properties" },
    ],
    outcomes: [
      { id: "o-added", kind: "outcome", title: "3,104 portfolios received insights", from: "Each advised investor’s holdings", summary: "Property Insights read client portfolios and wrote grounded cards into the investor app. Joseph Mews does not own these units. Nobody was contacted.", status: "recorded", when: "Today, 07:40", honesty: "illustrative", worker: "property-insights", block: "properties", sentTo: ["Properties block", "Company intelligence"] },
      { id: "o-holdings", kind: "outcome", title: "Client holdings read", from: "Advised investors’ portfolios", summary: "2,140 holdings belong to Joseph Mews clients. They are the input the worker reads. They were not edited.", status: "recorded", when: "Yesterday, 15:10", honesty: "illustrative", worker: "property-insights", block: "properties", sentTo: ["Properties block", "Company intelligence"] },
      { id: "o-risk", kind: "outcome", title: "412 concentration cards written", from: "Per-investor portfolio checks", summary: "412 advised investors received a concentration card in their app. London is the largest cluster. The worker did not contact them or advise a trade.", status: "recorded", when: "Today, 08:15", honesty: "illustrative", worker: "property-insights", block: "properties", sentTo: ["Properties block", "Company intelligence"] },
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
  observed: { label: "Observation", tone: "blue" },
  pattern: { label: "Observation", tone: "blue" },
  proposed: { label: "Recommendation", tone: "warn" },
  rule: { label: "In force", tone: "good" },
};

export const KNOWLEDGE_LAYER = {
  observation: { label: "Observation", tone: "blue" as const },
  recommendation: { label: "Recommendation", tone: "warn" as const },
  decision: { label: "Human decision", tone: "good" as const },
  outcome: { label: "Measured outcome", tone: "" as const },
};

export const SHEET_CLASS =
  "fixed inset-y-0 right-0 top-0 left-auto flex h-full max-h-none w-full max-w-[min(540px,100%)] translate-x-0 translate-y-0 flex-col gap-0 overflow-y-auto rounded-none border-y-0 border-l border-white/10 bg-popover text-popover-foreground p-0 shadow-[-20px_0_50px_-20px_rgba(0,0,0,.65)] sm:max-w-[min(540px,100%)] data-[state=open]:zoom-in-100";
