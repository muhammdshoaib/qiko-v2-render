export const PIPELINE_STAGES = [
  "cold_lead",
  "contacted",
  "in_discussion",
  "proposal_sent",
  "negotiation",
  "confirmed",
  "charged",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];

export const STAGE_LABEL: Record<PipelineStage, string> = {
  cold_lead: "Cold Lead",
  contacted: "Contacted",
  in_discussion: "In Discussion",
  proposal_sent: "Proposal Sent",
  negotiation: "Negotiation",
  confirmed: "Confirmed",
  charged: "Charged",
};

export type InvoiceStatus = "paid" | "unpaid" | "partial" | "overdue";
export type TaskStatus = "open" | "done";
export type TaskPriority = "low" | "normal" | "high";
export type ActivityKind = "human" | "agent" | "system";

export type Company = {
  id: string;
  name: string;
  sector: string;
  location: string;
  owner: string;
  website: string;
  summary: string;
};

export type Contact = {
  id: string;
  companyId: string;
  name: string;
  role: string;
  email: string;
  phone: string;
};

export type Opportunity = {
  id: string;
  companyId: string;
  title: string;
  value: number;
  expectedRevenue: number;
  estimatedCost?: number;
  owner: string;
  stage: PipelineStage;
  nextStep: string;
  lastActivityAt: string;
  createdAt: string;
};

export type Invoice = {
  id: string;
  companyId: string;
  opportunityId: string | null;
  number: string;
  amount: number;
  paidAmount: number;
  status: InvoiceStatus;
  dueDate: string;
  issuedAt: string;
};

export type Commitment = {
  id: string;
  companyId: string;
  title: string;
  cadence: string;
  amount: number;
  nextDate: string;
};

export type Task = {
  id: string;
  companyId: string;
  opportunityId: string | null;
  title: string;
  owner: string;
  dueDate: string;
  priority: TaskPriority;
  status: TaskStatus;
  source: "manual" | "agent";
  suggestedAction?: string;
};

export type Activity = {
  id: string;
  companyId: string;
  opportunityId: string | null;
  at: string;
  kind: ActivityKind;
  title: string;
  detail: string;
};

export type AgentSuggestion = {
  id: string;
  companyId: string;
  opportunityId: string | null;
  message: string;
  actionLabel: string;
  action: "follow_up" | "stage_review" | "invoice_nudge" | "email_sent";
  applied?: boolean;
};

export type DemoWorkflowId = "stalled" | "meeting" | "invoice";
export type ChannelScenarioId =
  | "claude-status"
  | "claude-email"
  | "slack-sales-ops"
  | "slack-sales-finance"
  | "slack-revenue-summary"
  | "slack-revenue-finance"
  | "slack-revenue-denied";
export type AgentEventSource = DemoWorkflowId | ChannelScenarioId;
export type DemoUserId = "maya" | "owen";
export type ChannelId = "claude" | "slack-sales" | "slack-revenue" | "email";
export type WorkflowRunStatus = "idle" | "in_progress" | "awaiting_owner" | "awaiting_approval" | "complete";
export type ChannelRunStatus = "idle" | "awaiting_approval" | "complete" | "blocked";
export type WorkflowFilter = "allowed" | "blocked" | "approval" | "completed";

export type ChannelRun = {
  id: ChannelScenarioId;
  status: ChannelRunStatus;
  completedSteps: string[];
};

export type ChannelMessage = {
  id: string;
  surface: "claude" | "slack-sales" | "slack-revenue";
  userId: DemoUserId;
  role: "user" | "agent" | "system";
  text: string;
  at: string;
  scenarioId: ChannelScenarioId;
  outcome: WorkflowFilter;
};

export type EmailDraft = {
  to: string;
  toName: string;
  subject: string;
  body: string;
  approved: boolean;
} | null;

export type WorkflowEvent = {
  id: string;
  workflowId: AgentEventSource;
  step: string;
  title: string;
  detail: string;
  at: string;
  filter: WorkflowFilter;
  edgeId: string;
  focus: string;
  crmHref?: string;
};

export type WorkflowRun = {
  id: DemoWorkflowId;
  status: WorkflowRunStatus;
  completedSteps: string[];
  pendingApproval?: {
    opportunityId: string;
    from: PipelineStage;
    to: PipelineStage;
    reason: string;
  } | null;
};

export type CrmState = {
  companies: Company[];
  contacts: Contact[];
  opportunities: Opportunity[];
  invoices: Invoice[];
  commitments: Commitment[];
  tasks: Task[];
  activities: Activity[];
  suggestions: AgentSuggestion[];
  workflowEvents: WorkflowEvent[];
  workflowRuns: WorkflowRun[];
  channelRuns: ChannelRun[];
  channelMessages: ChannelMessage[];
  emailDraft: EmailDraft;
};
