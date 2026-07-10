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
export const me = () => request<{ id: string; email: string; role: string }>("/auth/me");

// Agents (workers)
export type Agent = { id: string; name: string; status: string; atype: string; config: Record<string, unknown> };
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
export const ask = (conversation_id: string, question: string) =>
  request<{ role: string; text: string }>("/chat/ask", {
    method: "POST",
    body: JSON.stringify({ conversation_id, question }),
  });

// Grounded batch answering (confidence + citations + human-review gate) + xlsx export
export type BatchAnswer = { id: string; question: string; answer: string; confidence: number; decision: string; citations: string[] };
export const batchAnswer = (questions: string[]) =>
  request<BatchAnswer[]>("/agents/batch-answer", { method: "POST", body: JSON.stringify({ questions }) });
export async function batchExportUrl(questions: string[]): Promise<string> {
  const res = await fetch(`${BASE}/agents/batch-export`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ questions }),
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
export type RfpPack = { id: string; tenant: string; agent_id: string; title: string; client_name: string; deadline: string | null; stage: string; created_at: string };
export const listRfpPacks = (agentId: string) => request<RfpPack[]>(`/rfp/packs?agent_id=${encodeURIComponent(agentId)}`);
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
