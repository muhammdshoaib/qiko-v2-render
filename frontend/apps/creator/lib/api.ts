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
export const createAgent = (name: string, plan = "free") =>
  request<Agent>("/agents", { method: "POST", body: JSON.stringify({ name, plan }) });
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

// Billing
export type Subscription = { customer_id: string; plan?: string; status: string };
export const subscriptionStatus = (customerId: string) =>
  request<Subscription>(`/billing/subscription/${encodeURIComponent(customerId)}`);
export type BillingPlan = { id: number; name: string; price_id: string; amount: number; interval: string; display_price: string; worker_limit: number; features: string[] };
export const listPlans = () => request<BillingPlan[]>("/billing/plans");
export const startCheckout = (customerId: string, plan: string, priceId: string) =>
  request<{ url: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ customer_id: customerId, plan, price_id: priceId }) });
