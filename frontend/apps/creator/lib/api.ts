// Thin client for the qiko-core API. Cookies (httpOnly qiko_access + CSRF) are sent automatically
// with credentials: "include"; nothing is stored in localStorage.
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Double-submit CSRF: the server sets a readable (non-httpOnly) qiko_csrf cookie and requires it
// echoed back as a header on state-changing requests (currently /auth/logout and /auth/refresh).
function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie.match(/(?:^|; )qiko_csrf=([^;]+)/)?.[1];
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const csrf = csrfToken();
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "x-csrf-token": csrf } : {}),
      ...(opts.headers ?? {}),
    },
    ...opts,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.status === 204 ? (null as T) : ((await res.json()) as T);
}

// Auth
export const login = (email: string, password: string) =>
  request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => request("/auth/logout", { method: "POST" });
export const me = async () => {
  const res = await request<{ user: { id: string; email: string; role: string } }>("/auth/me");
  return res.user;
};

// Agents (workers)
export type Agent = { id: string; tenant: string; name: string; status: string; atype: string; config: Record<string, unknown>; created_at: string };
export const listAgents = () => request<Agent[]>("/agents");
export const createAgent = (name: string, atype: "worker" | "pre_sales_writer" | "sales_intelligence" | "finance" = "worker") =>
  request<Agent>("/agents", { method: "POST", body: JSON.stringify({ name, atype }) });
export const markReady = (id: string) => request<Agent>(`/agents/${id}/ready`, { method: "POST" });
export const updateAgentConfig = (id: string, patch: Record<string, unknown>) =>
  request<Agent>(`/agents/${id}/config`, { method: "PUT", body: JSON.stringify({ patch }) });

// Connections: Voice (Vapi.ai) + Calendly
export type VapiCredentials = { vapi_credentials_added: boolean; vapi_assistant_id: string; vapi_public_key: string; vapi_api_key_masked: string };
export const getVapiCredentials = (agentId: string) => request<VapiCredentials>(`/agents/${agentId}/vapi-credentials`);
export const saveVapiCredentials = (agentId: string, body: { vapi_assistant_id: string; vapi_public_key: string; vapi_api_key: string }) =>
  request<VapiCredentials>(`/agents/${agentId}/vapi-credentials`, { method: "POST", body: JSON.stringify(body) });
export const updateCalendlyEventType = (agentId: string, calendly_event_type: string) =>
  request<Agent>(`/agents/${agentId}/calendly-event-type`, { method: "PUT", body: JSON.stringify({ calendly_event_type }) });

// Connections: Salesforce (client-credentials grant against the tenant's own Connected App --
// reusable per-worker, same shape as Vapi, not customer-specific -- see integrations/clients.py)
export type SalesforceCredentials = { salesforce_credentials_added: boolean; instance_url: string; client_id_masked: string };
export const getSalesforceCredentials = (agentId: string) => request<SalesforceCredentials>(`/agents/${agentId}/salesforce-credentials`);
export const saveSalesforceCredentials = (agentId: string, body: { client_id: string; client_secret: string; instance_url: string }) =>
  request<SalesforceCredentials>(`/agents/${agentId}/salesforce-credentials`, { method: "POST", body: JSON.stringify(body) });
export const disconnectSalesforce = (agentId: string) =>
  request<{ disconnected: boolean }>(`/agents/${agentId}/salesforce-credentials`, { method: "DELETE" });
export const testSalesforceConnection = (agentId: string) =>
  request<{ ok: boolean }>(`/agents/${agentId}/salesforce-credentials/test`, { method: "POST" });

// Connections: Microsoft Teams (notifications via a per-tenant Incoming Webhook)
export type TeamsWebhookStatus = { connected: boolean; connected_at: string | null };
export const getTeamsWebhookStatus = () => request<TeamsWebhookStatus>("/channels/teams/webhook");
export const connectTeamsWebhook = (webhook_url: string) =>
  request<TeamsWebhookStatus>("/channels/teams/webhook", { method: "PUT", body: JSON.stringify({ webhook_url }) });
export const disconnectTeamsWebhook = () => request<TeamsWebhookStatus>("/channels/teams/webhook", { method: "DELETE" });
export const testTeamsWebhook = () => request<{ sent: boolean }>("/channels/teams/test", { method: "POST" });

// Knowledge + chat
export type Doc = { doc_id: string; chunks: number };
export const ingest = (doc_id: string, text: string) =>
  request<{ doc_id: string; chunks: number }>("/knowledge/ingest", {
    method: "POST",
    body: JSON.stringify({ doc_id, text }),
  });
export const listDocuments = () => request<Doc[]>("/knowledge/documents");
export const deleteDocument = (docId: string) =>
  request<{ removed: number }>(`/knowledge/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
export const ask = (conversation_id: string, question: string, agent_id?: string) =>
  request<{ role: string; text: string }>("/chat/ask", {
    method: "POST",
    body: JSON.stringify({ conversation_id, question, agent_id }),
  });

// Grounded batch answering (confidence + citations + human-review gate) + xlsx export
export type BatchAnswer = { id: string; question: string; answer: string; confidence: number; decision: string; citations: string[] };
export const batchAnswer = (questions: string[], agent_id?: string) =>
  request<BatchAnswer[]>("/agents/batch-answer", { method: "POST", body: JSON.stringify({ questions, agent_id }) });
export async function batchExportUrl(questions: string[], agent_id?: string): Promise<string> {
  const res = await fetch(`${BASE}/agents/batch-export`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ questions, agent_id }),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return URL.createObjectURL(await res.blob());
}

// Worker knowledge sources
const src = (agentId: string, kind: string, body: object) =>
  request<{ doc_id: string }>(`/agents/${agentId}/sources/${kind}`, { method: "POST", body: JSON.stringify(body) });
export const addBehavior = (agentId: string, source_id: string, text: string) =>
  src(agentId, "behaviors", { source_id, text });
export const addFaq = (agentId: string, source_id: string, question: string, answer: string) =>
  src(agentId, "faqs", { source_id, question, answer });
export const addPolicy = (agentId: string, source_id: string, title: string, body: string) =>
  src(agentId, "policies", { source_id, title, body });
export const addWebsite = (agentId: string, source_id: string, name: string, url: string, details: string) =>
  src(agentId, "websites", { source_id, name, url, details });

// Teams
export type Team = { team_id: string; members: Record<string, string> };
export const createTeam = (owner_id: string) =>
  request<Team>("/teams", { method: "POST", body: JSON.stringify({ owner_id }) });
export const addTeamMember = (teamId: string, user_id: string, role: string) =>
  request<Team>(`/teams/${teamId}/members`, { method: "POST", body: JSON.stringify({ user_id, role }) });

// RFP packs (tenders a worker is answering) + section assignments
export type RfpPack = {
  id: string; tenant: string; agent_id: string; title: string; client_name: string; deadline: string | null;
  stage: string; created_at: string;
  outcome: "won" | "lost" | "withdrawn" | null; outcome_reason: string; outcome_value: number | null; outcome_at: string | null;
};
export const listRfpPacks = (agentId: string) => request<RfpPack[]>(`/rfp/packs?agent_id=${encodeURIComponent(agentId)}`);
export const createRfpPack = (agentId: string, title: string, client_name = "", deadline: string | null = null) =>
  request<RfpPack>("/rfp/packs", { method: "POST", body: JSON.stringify({ agent_id: agentId, title, client_name, deadline }) });

// Win/Loss Analysis
export type PackStats = {
  total_decided: number; won: number; lost: number; withdrawn: number; pending: number;
  win_rate: number | null; won_value: number; lost_value: number; loss_reasons: Record<string, number>;
};
export const getPackStats = (agentId?: string) =>
  request<PackStats>(`/rfp/packs/stats${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ""}`);
export const setPackOutcome = (packId: string, outcome: "won" | "lost" | "withdrawn" | null, reason = "", value: number | null = null) =>
  request<RfpPack>(`/rfp/packs/${packId}/outcome`, { method: "PUT", body: JSON.stringify({ outcome, reason, value }) });
export type PackRequirement = { id: string; pack_id: string; req_id: string; title: string; classification: string; requirement: string };
export const listRequirements = (packId: string) => request<PackRequirement[]>(`/rfp/packs/${packId}/requirements`);
export const getRfpPack = (packId: string) => request<RfpPack & { document_text: string }>(`/rfp/packs/${packId}`);
export const askBidContext = (packId: string, question: string) =>
  request<{ question: string; answer: string }>(`/rfp/packs/${packId}/ask`, {
    method: "POST", body: JSON.stringify({ question }),
  });

export type ComplianceItem = { requirement: string; category: string; mandatory: boolean; owner: "AI" | "Human"; note: string };
export type TenderBrief = {
  summary: string; scope: string; submission_format: string;
  key_dates: string[]; success_criteria: string[]; gaps_and_risks: string[];
};

async function postDocumentText<T>(path: string, documentText: string): Promise<T> {
  const csrf = document.cookie.match(/(?:^|; )qiko_csrf=([^;]+)/)?.[1];
  const form = new FormData();
  form.append("file", new Blob([documentText], { type: "text/plain" }), "tender.txt");
  const res = await fetch(`${BASE}${path}`, {
    method: "POST", credentials: "include", body: form,
    headers: csrf ? { "x-csrf-token": csrf } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json() as Promise<T>;
}
export const tenderBrief = (packId: string, documentText: string) =>
  postDocumentText<TenderBrief>(`/rfp/packs/${packId}/brief`, documentText);
export const complianceCheck = (packId: string, documentText: string) =>
  postDocumentText<ComplianceItem[]>(`/rfp/packs/${packId}/compliance`, documentText);

export const exportUrl = (packId: string, kind: "xlsx" | "docx-clean" | "docx-review") => `${BASE}/rfp/packs/${packId}/export/${kind}`;

export type OpportunityScore = {
  score: number; qualified: boolean; rationale: string;
  criteria_results: { criterion: string; met: boolean; note: string }[];
};
export const scoreOpportunity = (packId: string) => request<OpportunityScore>(`/rfp/packs/${packId}/score`, { method: "POST" });
export const extractFromUrl = (packId: string, url: string) =>
  request<unknown[]>(`/rfp/packs/${packId}/extract-url`, { method: "POST", body: JSON.stringify({ url }) });

export type Answer = {
  req_id: string; req_title: string; classification: string; requirement: string;
  answer: string; confidence: number; grounding: number; status: string;
  citations: string[]; note: string;
};
export const getAnswers = (packId: string, force = false) =>
  request<Answer[]>(`/rfp/packs/${packId}/answers${force ? "?force=true" : ""}`);

export const submitFeedback = (packId: string, req_id: string, decision: "Approve" | "Edit" | "Reject", comment = "") =>
  request<{ req_id: string; decision: string; saved: boolean }>(`/rfp/packs/${packId}/feedback`, {
    method: "POST", body: JSON.stringify({ req_id, decision, comment }),
  });

// ── Pre-Sales / RFP tender cockpit (pre_sales_writer) ────────────────────────
// The section->question tree model backing the tender cockpit (app.modules.rfp.tree). A pack owns
// sections; each section owns questions, each carrying a grounded AI draft + an editable/lockable
// human draft. Reads are open to any authenticated viewer; mutations need Editor+. Base path is
// /rfp/packs/{id} (the same prefix as the pack CRUD/answers/export fns above).

/** Drafting pipeline stage (distinct from Win/Loss `outcome`). Mirrors rfp.service.STAGES. */
export const PACK_STAGES = ["parsed", "assigned", "drafting", "review", "final"] as const;
export type PackStage = (typeof PACK_STAGES)[number];

/** Section status vocabulary, mirroring rfp.tree.SECTION_STATUSES. */
export type PackSectionStatus =
  | "not_generated" | "generating" | "draft_ready" | "reviewing" | "locked" | "manual" | "overdue";

export type PackQuestion = {
  id: string; tenant: string; pack_id: string; section_id: string; text: string; req_id: string;
  word_limit: number | null; ai_answer: string; ai_sources: string[]; confidence: number;
  decision: string; kb_gap: boolean; locked: boolean; user_draft: string; order_index: number;
};

export type PackSection = {
  id: string; tenant: string; pack_id: string; code: string; name: string; page: number | null;
  weighting: string; status: PackSectionStatus; parent_id: string | null;
  assigned_reviewer_user_id: string | null; assigned_reviewer_name: string; due_date: string | null;
  // Stepper (Upload -> Parsed -> Assigned -> Drafting -> Review) per-section reviewer: a tenant
  // user id plus a denormalised display name so the Reviewer column renders without a join.
  reviewer: string | null; reviewer_name: string;
  manual: boolean; kb_gap: boolean; order_index: number;
};

/** One node of GET /sections: a section plus its nested questions and their averaged confidence. */
export type PackSectionNode = PackSection & { questions: PackQuestion[]; avg_confidence: number };

export type PackOverview = {
  sections: number; sections_locked: number; questions: number;
  ai_drafted: number; ai_drafted_total: number; for_human_review: number;
  kb_sources: number; kb_gaps: number; can_finalize: boolean;
};

export const getPackOverview = (packId: string) =>
  request<PackOverview>(`/rfp/packs/${packId}/overview`);

export const setPackStage = (packId: string, stage: PackStage) =>
  request<RfpPack>(`/rfp/packs/${packId}/stage`, { method: "PUT", body: JSON.stringify({ stage }) });

// ── Stepper (Upload -> Parsed -> Assigned -> Drafting -> Review) ─────────────
// The tender-generation background job's per-artifact progress. The Sections tab polls
// GET /status (~3s) while anything is pending/running and derives the stepper state from it.
export type GenState = "pending" | "running" | "ready" | "error";
export type TenderGenStatus = {
  requirements?: GenState;
  sections?: GenState;
  brief?: GenState;
  compliance?: GenState;
  drafts?: { state: GenState; done: number; total: number };
  assignments_confirmed?: boolean;
  updated_at?: string;
  error?: string | null;
};
export const getTenderStatus = (packId: string) =>
  request<TenderGenStatus>(`/rfp/packs/${packId}/status`);

/** A tenant user, for the per-section Reviewer assign dropdown. */
export type Assignee = { id: string; name: string; email: string };
export const getAssignees = (packId: string) =>
  request<Assignee[]>(`/rfp/packs/${packId}/assignees`);

/** Set (reviewer = user id) or clear (reviewer = null) a section's stepper reviewer. */
export const setSectionReviewer = (packId: string, sectionId: string, reviewer: string | null, reviewer_name = "") =>
  request<PackSection>(`/rfp/packs/${packId}/sections/${sectionId}/reviewer`, {
    method: "PUT", body: JSON.stringify({ reviewer, reviewer_name }),
  });

/** Stepper's "Confirm Assignments" button (Assigned -> Drafting). Sets assignments_confirmed=true. */
export const confirmAssignments = (packId: string) =>
  request<TenderGenStatus>(`/rfp/packs/${packId}/confirm-assignments`, { method: "POST" });

export const listPackSections = (packId: string) =>
  request<PackSectionNode[]>(`/rfp/packs/${packId}/sections`);

export type AddSectionBody = {
  code?: string; name: string; page?: number | null; weighting?: string; parent_id?: string | null;
  assigned_reviewer_name?: string; due_date?: string | null; manual?: boolean;
};
export const addPackSection = (packId: string, body: AddSectionBody) =>
  request<PackSection>(`/rfp/packs/${packId}/sections`, { method: "POST", body: JSON.stringify(body) });
export const updatePackSection = (packId: string, sectionId: string, patch: Partial<AddSectionBody & { status: PackSectionStatus }>) =>
  request<PackSection>(`/rfp/packs/${packId}/sections/${sectionId}`, { method: "PATCH", body: JSON.stringify(patch) });
export const deletePackSection = (packId: string, sectionId: string) =>
  request<{ deleted: string }>(`/rfp/packs/${packId}/sections/${sectionId}`, { method: "DELETE" });

export const addPackQuestion = (packId: string, sectionId: string, body: { text: string; word_limit?: number | null }) =>
  request<PackQuestion>(`/rfp/packs/${packId}/sections/${sectionId}/questions`, { method: "POST", body: JSON.stringify(body) });
export const updatePackQuestion = (packId: string, questionId: string, patch: { text?: string; word_limit?: number | null }) =>
  request<PackQuestion>(`/rfp/packs/${packId}/questions/${questionId}`, { method: "PATCH", body: JSON.stringify(patch) });
export const deletePackQuestion = (packId: string, questionId: string) =>
  request<{ deleted: string }>(`/rfp/packs/${packId}/questions/${questionId}`, { method: "DELETE" });

export const savePackQuestionDraft = (packId: string, questionId: string, user_draft: string) =>
  request<PackQuestion>(`/rfp/packs/${packId}/questions/${questionId}/draft`, { method: "PUT", body: JSON.stringify({ user_draft }) });
export const lockPackQuestion = (packId: string, questionId: string) =>
  request<PackQuestion>(`/rfp/packs/${packId}/questions/${questionId}/lock`, { method: "POST" });
export const unlockPackQuestion = (packId: string, questionId: string) =>
  request<PackQuestion>(`/rfp/packs/${packId}/questions/${questionId}/unlock`, { method: "POST" });
export const lockAllInPackSection = (packId: string, sectionId: string) =>
  request<PackSection>(`/rfp/packs/${packId}/sections/${sectionId}/lock-all`, { method: "POST" });

export const generatePackQuestion = (packId: string, questionId: string) =>
  request<PackQuestion>(`/rfp/packs/${packId}/questions/${questionId}/generate`, { method: "POST" });
export const generatePackSection = (packId: string, sectionId: string) =>
  request<PackQuestion[]>(`/rfp/packs/${packId}/sections/${sectionId}/generate`, { method: "POST" });
export const generatePack = (packId: string) =>
  request<PackQuestion[]>(`/rfp/packs/${packId}/generate`, { method: "POST" });

/** Upload an RFP/tender document to a pack: extracts requirements and (re)builds the section tree. */
export async function extractPack(packId: string, file: File): Promise<PackRequirement[]> {
  const csrf = csrfToken();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/rfp/packs/${packId}/extract`, {
    method: "POST", credentials: "include", body: form,
    headers: csrf ? { "x-csrf-token": csrf } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

/** Fetch an export (xlsx / clean docx / annotated review docx) as a Blob for client-side download. */
export async function exportPackBlob(packId: string, kind: "xlsx" | "docx-clean" | "docx-review"): Promise<Blob> {
  const res = await fetch(exportUrl(packId, kind), { credentials: "include" });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.blob();
}

export async function ingestFile(docId: string, file: File): Promise<{ chunks: number }> {
  const csrf = document.cookie.match(/(?:^|; )qiko_csrf=([^;]+)/)?.[1];
  const form = new FormData();
  form.append("file", file);
  form.append("doc_id", docId);
  const res = await fetch(`${BASE}/knowledge/ingest-file`, {
    method: "POST", credentials: "include", body: form,
    headers: csrf ? { "x-csrf-token": csrf } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

// Leads captured through public forms (enterprise / RAG-wired) -- shown as a lightweight CRM.
export type Lead = { id: string; kind: string; name: string; email: string; payload: Record<string, unknown>; created_at: string };
export const listLeads = () => request<Lead[]>("/leads");

// CRM / Sales Pipeline -- real prospects derived from a worker's own chat history (app.modules.crm).
export type CrmContact = {
  id: string; agentId: string; conversationId: string | null; name: string; email: string | null;
  phone: string | null; status: "new" | "contacted" | "interested" | "quoted" | "converted" | "lost";
  estimatedValue: number; currency: string; aiSummary: string | null; sentiment: string | null;
  keyTopics: string[]; createdAt: string; updatedAt: string;
};
export type CrmPipeline = { contacts: CrmContact[]; total: number; dashboard: { statusBreakdown: Record<string, number> } };
export const getCrmPipeline = (agentId: string) => request<CrmPipeline>(`/crm/${agentId}`);

export type CrmTimelineEvent = { type: string; role: string; title: string; summary: string; timestamp: string };
export type CrmAction = { id: string; contactId: string; actionType: string; title: string; description: string; priority: string; status: string; createdAt: string };
export type CrmContactDetail = {
  contact: CrmContact; timeline: CrmTimelineEvent[]; actions: CrmAction[]; bookings: unknown[];
  stats: { messageCount: number; voiceCallCount: number; emailCount: number };
};
export const getCrmContact = (contactId: string) => request<CrmContactDetail>(`/crm/contacts/${contactId}`);

export const updateCrmContact = (contactId: string, patch: Partial<{
  name: string; email: string; phone: string; status: string; estimated_value: number;
}>) => request<CrmContact>(`/crm/contacts/${contactId}`, { method: "PATCH", body: JSON.stringify(patch) });

export const generateCrmSummary = (contactId: string) =>
  request<CrmContact>(`/crm/contacts/${contactId}/summary`, { method: "POST" });

export const addCrmAction = (contactId: string, title: string, opts: { actionType?: string; description?: string; priority?: string } = {}) =>
  request<CrmAction>(`/crm/contacts/${contactId}/actions`, {
    method: "POST", body: JSON.stringify({ title, action_type: opts.actionType, description: opts.description, priority: opts.priority }),
  });

export const updateCrmAction = (actionId: string, status: string) =>
  request<CrmAction>(`/crm/actions/${actionId}`, { method: "PATCH", body: JSON.stringify({ status }) });

export const syncCrmContactToSalesforce = (contactId: string) =>
  request<{ synced: boolean; salesforce_id: string | null }>(`/crm/contacts/${contactId}/sync-salesforce`, { method: "POST" });

// Sales Intelligence (IDG Sales) -- opportunity ingestion/qualification/review/Salesforce-push
// worker. Backend module is being built in parallel (expected at app.modules.sales_intelligence
// in qiko-core, mirrored on app.modules.crm's per-agent REST shape: `/sales-intelligence/{agentId}/...`
// for agent-scoped reads, plain resource dicts in camelCase (not the old Laravel
// {success,data,errors} envelope) -- these functions encode that *assumed* contract pending the
// real router; endpoint names/paths are taken 1:1 from the Laravel IdgSalesController's public
// methods (sources, updateSource, scanUngm, scanTed, opportunities, opportunity, createOpportunity,
// updateOpportunity, opportunityHistory, archiveOpportunity, restoreOpportunity, deleteOpportunity,
// activityLogs, scanHistory, review, saveNotes, salesforceStatus, salesforceConnect,
// salesforceDisconnect, pushToSalesforce) and its Resources (IdgSalesOpportunityResource,
// IdgSalesIngestionSourceResource, IdgSalesActivityLogResource).
export const OPPORTUNITY_STAGES = [
  "ingested", "qualifying", "qualified", "awaiting_review", "validated",
  "ready_salesforce", "push_pending", "pushed", "rejected", "push_failed",
] as const;
export type OpportunityStage = (typeof OPPORTUNITY_STAGES)[number];
export type Recommendation = "Bid" | "Review" | "No Bid";

export type SalesIntelSource = {
  id: number; agentId: string; sourceKey: "ted" | "ungm"; name: string; type: string;
  status: "active" | "inactive" | "paused" | string; authStatus: string | null;
  scanCadence: string; scanIntervalMinutes: number; lastScanStatus: string | null;
  lastScanAt: string | null; nextScanAt: string | null; opportunitiesFound: number;
  lastError: string | null; config: Record<string, unknown>; createdAt: string; updatedAt: string;
};

export type OpportunityContact = { name: string | null; email: string | null; phone: string | null };

export type OpportunityDetail = {
  overview: {
    deadlineAt: string | null; estimatedValue: number | null; currency: string | null;
    country: string | null; category: string | null; buyer: string | null; source: string | null;
    sourceUrl: string | null; publishedAt: string | null; extractionConfidence: number | null;
    securityClearance: string | null; contacts: OpportunityContact[]; framework: string | null;
    contractDuration: string | null; technology: string | null; reference: string | null;
    noticeType: string | null;
  };
  summary: {
    executiveSummary: string | null; riskSummary: string | null; opportunitySummary: string | null;
    requirements: string[]; deliverables: string[];
  };
  qualification: {
    overallScore: number | null; recommendation: Recommendation | null; confidence: number | null;
    dimensions: Record<string, number>; aiReasoning: string | null; recommendations: string[];
    reasons: string[]; risks: string[]; rejectionReasons: string[];
  };
  completed: {
    isComplete: boolean; stage: OpportunityStage; humanReviewStatus: string | null;
    reviewedBy: { id: number; userName: string; email: string } | null; reviewedAt: string | null;
    salesforcePushStatus: string | null; salesforceOpportunityId: string | null;
    salesforcePushedAt: string | null; salesforcePushError: string | null; completedAt: string | null;
  };
  notes: { humanReviewNotes: string | null; updatedAt: string | null };
};

export type SalesOpportunity = {
  id: number; agentId: string; externalId: string | null; sourceKey: "ted" | "ungm" | string;
  source: string | null; sourceUrl: string | null; isManual: boolean; title: string;
  buyer: string | null; country: string | null; region: string | null; category: string | null;
  estimatedValue: number | null; currency: string | null; publishedAt: string | null;
  deadlineAt: string | null; stage: OpportunityStage; recommendation: Recommendation | null;
  qualificationScore: number | null; confidence: number | null; competitorReadiness: number | null;
  qualificationSummary: string | null; qualificationReasons: string[]; qualificationDimensions: Record<string, number>;
  qualificationRecommendations: string[]; rejectionReasons: string[]; risks: string[]; missingFields: string[];
  humanReviewStatus: string | null; humanReviewNotes: string | null;
  reviewedBy: { id: number; userName: string; email: string } | null; reviewedAt: string | null;
  assignedReviewerUserId: string | null; assignedReviewerName: string | null;
  assignedByUserId: string | null; assignedAt: string | null;
  archivedAt: string | null; isArchived: boolean;
  salesforcePushStatus: string | null; salesforceOpportunityId: string | null;
  salesforcePushedAt: string | null; salesforcePushError: string | null;
  createdAt: string; updatedAt: string; detail?: OpportunityDetail;
};

export type SalesActivityLog = {
  id: number; opportunityId: number | null; actorUserId: number | null;
  actor: { id: number; userName: string; email: string } | null; activityType: string;
  action: string; detail: string | null; tone: "success" | "info" | "warning" | "error" | string;
  changes: Record<string, unknown> | null; metadata: Record<string, unknown> | null;
  createdAt: string; updatedAt: string;
};

export type SalesScanHistoryEntry = {
  id: number; sourceKey: string; status: string; opportunitiesFound: number;
  startedAt: string | null; finishedAt: string | null; error: string | null;
};

export type SalesforceConnectionStatus = {
  connected: boolean; instanceUrl: string | null; status: "connected" | "disconnected" | string;
  connectedAt: string | null; lastPushAt: string | null;
};

const siQuery = (params: Record<string, string | number | boolean | undefined>) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== null) q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
};

export const listSalesSources = (agentId: string) =>
  request<{ sources: SalesIntelSource[] }>(`/sales-intelligence/${agentId}/sources`);
export const updateSalesSource = (agentId: string, sourceKey: "ted" | "ungm", status: string) =>
  request<{ source: SalesIntelSource }>(`/sales-intelligence/${agentId}/sources/${sourceKey}`, {
    method: "PATCH", body: JSON.stringify({ source_key: sourceKey, status }),
  });
export const scanTedSource = (agentId: string, body: Record<string, unknown> = {}) =>
  request<{ scanned: boolean; found: number }>(`/sales-intelligence/${agentId}/scan/ted`, {
    method: "POST", body: JSON.stringify(body),
  });
export const scanUngmSource = (agentId: string, body: Record<string, unknown> = {}) =>
  request<{ scanned: boolean; found: number }>(`/sales-intelligence/${agentId}/scan/ungm`, {
    method: "POST", body: JSON.stringify(body),
  });

export type SalesOpportunityFilters = {
  stage?: OpportunityStage; recommendation?: Recommendation; source_key?: string; title?: string;
  search?: string; limit?: number; include_archived?: boolean; archived_only?: boolean;
};
export const listSalesOpportunities = (agentId: string, filters: SalesOpportunityFilters = {}) =>
  request<{ opportunities: SalesOpportunity[]; summary: Record<string, unknown> }>(
    `/sales-intelligence/${agentId}/opportunities${siQuery(filters)}`,
  );
export const getSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}`);
export const createSalesOpportunity = (agentId: string, payload: Record<string, unknown>) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities`, {
    method: "POST", body: JSON.stringify(payload),
  });
export const updateSalesOpportunity = (agentId: string, opportunityId: number | string, payload: Record<string, unknown>) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}`, {
    method: "PATCH", body: JSON.stringify(payload),
  });
export const getSalesOpportunityHistory = (agentId: string, opportunityId: number | string) =>
  request<{ history: SalesActivityLog[] }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/history`);
export const archiveSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/archive`, { method: "POST" });
export const restoreSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/restore`, { method: "POST" });
export const deleteSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ deleted: boolean }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}`, { method: "DELETE" });

export const getSalesActivityLogs = (agentId: string, params: { opportunity_id?: number; page?: number; per_page?: number } = {}) =>
  request<{ logs: SalesActivityLog[]; total: number }>(`/sales-intelligence/${agentId}/activity-logs${siQuery(params)}`);
export const getSalesScanHistory = (agentId: string, params: { source_key?: string; per_page?: number } = {}) =>
  request<{ history: SalesScanHistoryEntry[] }>(`/sales-intelligence/${agentId}/scan-history${siQuery(params)}`);

export const reviewSalesOpportunity = (agentId: string, opportunityId: number | string, decision: "approve" | "reject", notes = "") =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/review`, {
    method: "POST", body: JSON.stringify({ decision, notes }),
  });
export const saveSalesOpportunityNotes = (agentId: string, opportunityId: number | string, notes: string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/notes`, {
    method: "POST", body: JSON.stringify({ notes }),
  });

export const getSalesforceStatus = (agentId: string) =>
  request<{ salesforce: SalesforceConnectionStatus }>(`/sales-intelligence/${agentId}/salesforce/status`);
export const connectSalesIntelSalesforce = (agentId: string) =>
  request<{ authorizeUrl: string }>(`/sales-intelligence/${agentId}/salesforce/connect`, { method: "POST" });
export const disconnectSalesIntelSalesforce = (agentId: string) =>
  request<{ salesforce: SalesforceConnectionStatus }>(`/sales-intelligence/${agentId}/salesforce/disconnect`, { method: "POST" });
export const pushOpportunityToSalesforce = (agentId: string, opportunityId: number | string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/push-to-salesforce`, { method: "POST" });

// Assign Reviewer -- PATCH assign-reviewer (editor role). Pass both null to clear the reviewer.
export const assignSalesReviewer = (
  agentId: string, opportunityId: number | string, body: { user_id?: string | null; name?: string | null },
) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/assign-reviewer`, {
    method: "PATCH", body: JSON.stringify(body),
  });

// Decision History -- the approve/reject/override audit trail for one opportunity.
export type SalesDecision = {
  id: string; agentId: string; opportunityId: string | null; action: string;
  decision: "approved" | "rejected" | "needs_review" | string | null; decisionLabel: string;
  detail: string | null; tone: string; reviewerUserId: string | null;
  metadata: Record<string, unknown>; createdAt: string;
};
export const getSalesOpportunityDecisions = (agentId: string, opportunityId: number | string) =>
  request<{ opportunityId: string; decisions: SalesDecision[] }>(
    `/sales-intelligence/${agentId}/opportunities/${opportunityId}/decisions`,
  );

// Generic in-app notifications (app.modules.notifications) -- tenant-scoped inbox, reusable across
// verticals. Sales Intelligence wires its triggers server-side (review-required, Salesforce sync
// success/failed, scan-failed, deadline-reminder). In-product only (no email/FCM push).
export type NotificationCategory = "sales_intelligence" | "general" | string;
export type Notification = {
  id: string; category: NotificationCategory; type: string; title: string; body: string;
  agentId: string | null; opportunityId: string | null; metadata: Record<string, unknown>;
  read: boolean; readAt: string | null; createdAt: string;
};
export const listNotifications = (params: { category?: NotificationCategory; unread_only?: boolean; limit?: number } = {}) =>
  request<{ notifications: Notification[]; unreadCount: number }>(`/notifications${siQuery(params)}`);
export const getUnreadNotificationCount = (category?: NotificationCategory) =>
  request<{ unreadCount: number }>(`/notifications/unread-count${siQuery({ category })}`);
export const markNotificationRead = (id: string) =>
  request<{ notification: Notification }>(`/notifications/${id}/read`, { method: "POST" });
export const markAllNotificationsRead = (category?: NotificationCategory) =>
  request<{ updated: number }>(`/notifications/read-all${siQuery({ category })}`, { method: "POST" });

// Public embed chat (no auth)
export const publicChat = (tenant: string, workerId: string, question: string) =>
  request<{ role: string; text: string }>("/public/chat", {
    method: "POST",
    body: JSON.stringify({ tenant, worker_id: workerId, question }),
  });

// Public /labs contact form (no auth -- a prospect doesn't have a tenant yet)
export type LabsContactBody = { name: string; work_email: string; company: string; company_size: string; build_request: string };
export const submitLabsContact = (body: LabsContactBody) =>
  request<{ success: boolean; message: string }>("/marketing/labs-contact", { method: "POST", body: JSON.stringify(body) });

// Billing -- the subscription subject is the authenticated tenant, derived server-side from the
// session cookie. No customer/tenant id is ever sent from the client (that was a cross-tenant
// BOLA); `customer_id` in the response is the caller's own tenant, kept for shape continuity.
export type Subscription = { customer_id: string; plan?: string; status: string; cancel_at_period_end?: boolean };
export const subscriptionStatus = () => request<Subscription>("/billing/subscription");
export type BillingPlan = { id: number; name: string; price_id: string; amount: number; interval: string; display_price: string; worker_limit: number; features: string[] };
export const listPlans = () => request<BillingPlan[]>("/billing/plans");
export const startCheckout = (plan: string, priceId: string) =>
  request<{ url: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ plan, price_id: priceId }) });
export const billingPortal = () => request<{ url: string }>("/billing/portal");
export const cancelSubscription = () =>
  request<Subscription>("/billing/subscription/cancel", { method: "POST" });
export const resumeSubscription = () =>
  request<Subscription>("/billing/subscription/resume", { method: "POST" });

// ── Finance (Financial Analyst) ──────────────────────────────────────────────
// Excel portfolio-analytics worker. The backend `finance` module is being built in parallel in
// qiko-core (app/modules/finance/router.py) under `/finance/{agentId}/...` on the `/api/v1` prefix,
// mirroring the existing per-agent module convention (app.modules.crm / app.modules.sales_intelligence:
// tenant-scoped via authed_tenant, plain camelCase resource dicts). These types/functions encode the
// *assumed* contract, taken 1:1 from the original Excel-Agent data shape (qiko-frontend `lib/ELApi.ts`:
// ELUserAnalyticsResponse / ELUserProperty / ELUserFinanceFile / ELChatResponse / ELHistoryResponse),
// pending the real router. TODO(finance-backend): reconcile field names once router.py exists --
// likely divergences flagged inline below.

/** One row from the `summary: [...]` array of keyed metrics (mirrors ELUserAnalyticsSummaryMetric).
 * The backend may instead return a flat object (legacy ELUserAnalyticsSummary); the client normalizes
 * both -- see components/finance/utils.ts:normalizeFinanceSummary. */
export type FinanceSummaryMetric = { key: string; label?: string; value?: number | string; formatted?: string; subtitle?: string };
export type FinanceSummary = FinanceSummaryMetric[] | {
  propertyCount?: number; vendorCount?: number; totalIncome?: number; totalExpenses?: number;
  netProfit?: number; outstanding?: number; expenseBreakdown?: { net?: number; vat?: number };
};

export type FinanceExpenseCategory = { category: string; amount: number };
export type FinanceTopVendor = { vendorName: string; amount: number };

/** Per-property analytics row (mirrors ELUserProperty). */
export type FinanceProperty = {
  propertyId?: string; name?: string; income?: number; expenses?: number; netProfit?: number;
  marginPercent?: number; outstanding?: number; costToIncomeRatio?: number; riskScore?: number;
  riskLevel?: string; profitabilityClass?: string;
  expenseCategories?: FinanceExpenseCategory[]; topVendors?: FinanceTopVendor[];
};

export type FinanceChartVendor = { vendorName: string; amount: number; sharePercent?: number };
export type FinanceChartIncomeExpense = { propertyId?: string; propertyName: string; income: number; expenses: number };
export type FinanceCharts = {
  incomeVsExpensesByProperty?: FinanceChartIncomeExpense[];
  topVendorsBySpend?: FinanceChartVendor[];
  // Some fields (profitabilityClassification, expenseCategories drilldown details) are optional/richer
  // in the original; the dashboard derives its donuts from properties[] when absent.
  [key: string]: unknown;
};

/** One insight inside a trend section (mirrors the { title, insightText } shape). */
export type FinanceTrendInsight = { title?: string; text?: string; insightText?: string };
export type FinanceTrendSection = { section?: string; title?: string; insights?: FinanceTrendInsight[] };
/** trends is typically `{ trends: FinanceTrendSection[] }` or `FinanceTrendSection[]`. */
export type FinanceTrends = { trends?: FinanceTrendSection[] } | FinanceTrendSection[] | Record<string, unknown>;

export type FinanceAnalytics = {
  status?: string;
  files?: { label: string; namespace: string; rowCount: number }[];
  totalFiles?: number;
  totalRows?: number;
  currency?: string;
  dateRange?: { from?: string; to?: string; label?: string };
  summary?: FinanceSummary;
  properties?: FinanceProperty[];
  charts?: FinanceCharts;
  insights?: Record<string, unknown> | unknown[];
  trends?: FinanceTrends;
};

export type FinanceFile = { id: string; label: string; namespace: string; rowCount: number; uploadedAt: string };
export type FinanceFilesResponse = { files: FinanceFile[]; totalFiles: number; totalRows: number };
export type FinanceChatMessage = { role: "user" | "assistant"; text: string };
export type FinanceChatResponse = { reply: string; sourcesUsed?: string[]; rowsRetrieved?: number };
export type FinanceHistoryItem = { role: "user" | "assistant"; content: string; timestamp: number };
export type FinanceHistoryResponse = { count: number; history: FinanceHistoryItem[] };

export const getFinanceAnalytics = (agentId: string, query: { from?: string; to?: string; month?: string } = {}) => {
  const q = new URLSearchParams();
  if (query.from) q.set("from", query.from);
  if (query.to) q.set("to", query.to);
  if (query.month) q.set("month", query.month);
  const s = q.toString();
  return request<FinanceAnalytics>(`/finance/${agentId}/analytics${s ? `?${s}` : ""}`);
};

export const listFinanceFiles = (agentId: string) => request<FinanceFilesResponse>(`/finance/${agentId}/files`);

// Deletes the given uploaded workbook namespaces. TODO(finance-backend): confirm whether DELETE
// carries a body (ids) or uses per-id path params -- assumed body { ids } here, echoing ELApi.
export const deleteFinanceFiles = (agentId: string, ids: string[]) =>
  request<{ success: boolean; deleted: string[]; deletedCount: number }>(`/finance/${agentId}/files`, {
    method: "DELETE", body: JSON.stringify({ ids }),
  });

export async function uploadFinanceFile(agentId: string, file: File): Promise<{ fileName: string; namespace?: string; totalRows?: number }> {
  const csrf = csrfToken();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/finance/${agentId}/upload`, {
    method: "POST", credentials: "include", body: form,
    headers: csrf ? { "x-csrf-token": csrf } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export const financeChat = (agentId: string, message: string) =>
  request<FinanceChatResponse>(`/finance/${agentId}/chat`, { method: "POST", body: JSON.stringify({ message }) });

export const getFinanceHistory = (agentId: string, limit = 100) =>
  request<FinanceHistoryResponse>(`/finance/${agentId}/history?limit=${limit}`);

export const clearFinanceHistory = (agentId: string) =>
  request<{ success: boolean }>(`/finance/${agentId}/history`, { method: "DELETE" });
