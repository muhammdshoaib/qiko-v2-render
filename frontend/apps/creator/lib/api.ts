// Thin client for the qiko-core API. Cookies (httpOnly qiko_access + CSRF) are sent automatically
// with credentials: "include"; nothing is stored in localStorage.
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function extractDetail(text: string): string {
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed.detail)) return parsed.detail.map((item: unknown) => String(item)).join(". ");
    if (typeof parsed.detail === "string") return parsed.detail;
    if (typeof parsed.message === "string") return parsed.message;
  } catch {
    // Not JSON; return the raw response.
  }
  return text;
}

// Double-submit CSRF: the server sets a readable (non-httpOnly) qiko_csrf cookie and requires it
// echoed back as a header on state-changing requests (currently /auth/logout and /auth/refresh).
function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie.match(/(?:^|; )qiko_csrf=([^;]+)/)?.[1];
}

// A single shared in-flight refresh so a burst of concurrent 401s triggers one /auth/refresh, not N.
let refreshInFlight: Promise<boolean> | null = null;
function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const csrf = csrfToken();
        const r = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrf-token": csrf } : {}) },
        });
        return r.ok;
      } catch {
        return false;
      }
    })();
    void refreshInFlight.finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

async function doFetch(path: string, opts: RequestInit): Promise<Response> {
  const csrf = csrfToken();
  const isFormData = typeof FormData !== "undefined" && opts.body instanceof FormData;
  const baseHeaders: Record<string, string> = {};
  if (csrf) baseHeaders["x-csrf-token"] = csrf;
  if (!isFormData) baseHeaders["Content-Type"] = "application/json";
  return fetch(`${BASE}${path}`, {
    credentials: "include",
    ...opts,
    headers: {
      ...baseHeaders,
      ...(opts.headers ?? {}),
    },
  });
}

// Only the token endpoints must NOT trigger a refresh-retry (that would loop). Everything else,
// including /auth/me, should refresh on a 401 so an expired access token does not surface an error.
const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout"];

async function requestResponse(path: string, opts: RequestInit = {}): Promise<Response> {
  let res = await doFetch(path, opts);
  // The access token is short-lived (15 min). On a 401, silently refresh once (using the long-lived
  // refresh cookie) and retry, so an active user is never kicked to login mid-session.
  if (res.status === 401 && !NO_REFRESH_PATHS.some((p) => path.startsWith(p))) {
    if (await refreshSession()) {
      res = await doFetch(path, opts);
    } else if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      // The refresh cookie is missing, expired or revoked. Stop rendering a broken authenticated
      // screen and let the user establish a new session. The login middleware allows refresh-only
      // visitors through precisely so a stale refresh cookie cannot create a redirect loop.
      window.location.assign("/login");
    }
  }
  if (!res.ok) throw new ApiError(res.status, extractDetail(await res.text()));
  return res;
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const response = await requestResponse(path, opts);
  return response.status === 204 ? (null as T) : ((await response.json()) as T);
}

async function requestBlob(path: string, opts: RequestInit = {}): Promise<Blob> {
  return (await requestResponse(path, opts)).blob();
}

export type ServerConsent = {
  decision_id: string; client_revision: number; preferences: boolean; analytics: boolean;
  marketing: boolean; terms_release_id: string; privacy_release_id: string;
  cookies_release_id: string; created_at: string;
};

export async function getAuthenticatedConsent(): Promise<ServerConsent | "anonymous" | "missing" | "retry"> {
  try {
    let response = await doFetch("/consent", { method: "GET" });
    if (response.status === 401 && await refreshSession()) response = await doFetch("/consent", { method: "GET" });
    if (response.ok) return await response.json() as ServerConsent;
    if (response.status === 401) return "anonymous";
    if (response.status === 404) return "missing";
    return "retry";
  } catch { return "retry"; }
}

export async function syncAuthenticatedConsent(body: Record<string, unknown>): Promise<"user" | "anonymous" | "stale" | "retry"> {
  try {
    let response = await doFetch("/consent", { method: "POST", body: JSON.stringify(body) });
    if (response.status === 401 && await refreshSession()) response = await doFetch("/consent", { method: "POST", body: JSON.stringify(body) });
    if (response.ok) return "user";
    if (response.status === 401) return "anonymous";
    if (response.status === 409) return "stale";
    return "retry";
  } catch { return "retry"; }
}
export const recordAnonymousConsent = (body: Record<string, unknown>) =>
  request<{ recorded: boolean }>("/consent/anonymous", { method: "POST", body: JSON.stringify(body) });
export const verifySignupEmail = (body: Record<string, unknown>) =>
  request<{ user_id: string; email: string; team_id: string | null; worker_id?: string }>("/auth/verify-email", {
    method: "POST", body: JSON.stringify(body),
  });

// Auth
export const login = (email: string, password: string) =>
  request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => request("/auth/logout", { method: "POST" });
export const me = async () => {
  const res = await request<{ user: { id: string; email: string; name: string | null; role: string; twofa_enabled: boolean } }>("/auth/me");
  return res.user;
};
// Update the current user's own profile (display name). CSRF header is auto-added by request().
export const updateProfile = (name: string) =>
  request<{ user: { id: string; email: string; name: string | null; role: string } }>("/auth/me", {
    method: "PATCH", body: JSON.stringify({ name }),
  });

// Two-factor authentication (voluntary in Creator; mandatory once enabled)
export const twofaSetup = () =>
  request<{ secret: string; provisioning_uri: string }>("/auth/2fa/setup", { method: "POST" });
export const twofaVerify = (secret: string, code: string, password: string) =>
  request<{ enabled: boolean; reauthentication_required: boolean; backup_codes: string[] }>("/auth/2fa/verify-setup", {
    method: "POST", body: JSON.stringify({ secret, code, password }),
  });
export const regenerateBackupCodes = (password: string, currentCode: string) =>
  request<{ backup_codes: string[]; reauthentication_required: boolean }>("/auth/2fa/backup-codes/regenerate", {
    method: "POST", body: JSON.stringify({ password, current_code: currentCode }),
  });
// Non-redirecting session probe for client-side UI gating, including on public pages
// (onboarding/forgot-password/reset-password). Unlike me()/request(), a 401 here returns null instead
// of redirecting to /login, so anonymous visitors are simply treated as logged out. Mirrors
// getAuthenticatedConsent: refresh once on 401, then give up quietly.
export async function probeSession(): Promise<{ id: string; email: string; role: string } | null> {
  try {
    let response = await doFetch("/auth/me", { method: "GET" });
    if (response.status === 401 && (await refreshSession())) {
      response = await doFetch("/auth/me", { method: "GET" });
    }
    if (response.ok) {
      return ((await response.json()) as { user: { id: string; email: string; role: string } }).user;
    }
    return null;
  } catch {
    return null;
  }
}

// Agents (workers)
export type Agent = { id: string; tenant: string; name: string; status: string; atype: string; enabled: boolean; config: Record<string, unknown>; created_at: string };
export type AgentUsage = { used_count: number; worker_limit: number };
export const listAgents = async () =>
  (await request<Agent[]>("/agents")).filter((agent) => agent.enabled !== false);
export const getAgentUsage = () => request<AgentUsage>("/agents/usage");
export const createAgent = (name: string, atype: "worker" | "pre_sales_writer" | "sales_intelligence" | "finance" | "intelligence" = "worker") =>
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

// Connections: Calendly + ClickUp. Each worker stores the TENANT'S OWN token (encrypted server-side,
// only a masked preview comes back) -- there is no shared Qiko-owned account.
export type CalendlyCredentials = { calendly_credentials_added: boolean; calendly_event_type: string; token_masked: string };
export const getCalendlyCredentials = (agentId: string) => request<CalendlyCredentials>(`/agents/${agentId}/calendly-credentials`);
export const saveCalendlyCredentials = (agentId: string, token: string) =>
  request<CalendlyCredentials>(`/agents/${agentId}/calendly-credentials`, { method: "POST", body: JSON.stringify({ token }) });
export const disconnectCalendly = (agentId: string) =>
  request<{ disconnected: boolean }>(`/agents/${agentId}/calendly-credentials`, { method: "DELETE" });
export const testCalendlyConnection = (agentId: string) =>
  request<{ ok: boolean; user: string }>(`/agents/${agentId}/calendly-credentials/test`, { method: "POST" });

export type ClickUpCredentials = { clickup_credentials_added: boolean; default_list_id: string; token_masked: string };
export const getClickUpCredentials = (agentId: string) => request<ClickUpCredentials>(`/agents/${agentId}/clickup-credentials`);
export const saveClickUpCredentials = (agentId: string, body: { api_token: string; default_list_id: string }) =>
  request<ClickUpCredentials>(`/agents/${agentId}/clickup-credentials`, { method: "POST", body: JSON.stringify(body) });
export const disconnectClickUp = (agentId: string) =>
  request<{ disconnected: boolean }>(`/agents/${agentId}/clickup-credentials`, { method: "DELETE" });
export const testClickUpConnection = (agentId: string) =>
  request<{ ok: boolean; user: string }>(`/agents/${agentId}/clickup-credentials/test`, { method: "POST" });

// Connections: Slack (the tenant's own bot token) + Gmail (their own address + App Password).
export type SlackCredentials = { slack_credentials_added: boolean; default_channel: string; token_masked: string };
export const getSlackCredentials = (agentId: string) => request<SlackCredentials>(`/agents/${agentId}/slack-credentials`);
export const saveSlackCredentials = (agentId: string, body: { bot_token: string; default_channel: string }) =>
  request<SlackCredentials>(`/agents/${agentId}/slack-credentials`, { method: "POST", body: JSON.stringify(body) });
export const disconnectSlack = (agentId: string) =>
  request<{ disconnected: boolean }>(`/agents/${agentId}/slack-credentials`, { method: "DELETE" });
export const testSlackConnection = (agentId: string) =>
  request<{ ok: boolean; team: string; user: string }>(`/agents/${agentId}/slack-credentials/test`, { method: "POST" });

export type GmailCredentials = { gmail_credentials_added: boolean; address: string; app_password_masked: string };
export const getGmailCredentials = (agentId: string) => request<GmailCredentials>(`/agents/${agentId}/gmail-credentials`);
export const saveGmailCredentials = (agentId: string, body: { address: string; app_password: string }) =>
  request<GmailCredentials>(`/agents/${agentId}/gmail-credentials`, { method: "POST", body: JSON.stringify(body) });
export const disconnectGmail = (agentId: string) =>
  request<{ disconnected: boolean }>(`/agents/${agentId}/gmail-credentials`, { method: "DELETE" });
export const testGmailConnection = (agentId: string) =>
  request<{ ok: boolean; user: string }>(`/agents/${agentId}/gmail-credentials/test`, { method: "POST" });

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
export const testTeamsWebhook = (workerId: string) =>
  request<{ sent: boolean }>("/channels/teams/test", {
    method: "POST",
    body: JSON.stringify({ worker: workerId }),
  });

// Knowledge + chat
export type Doc = { doc_id: string; name?: string; chunks: number; agent_id?: string };
// agentId scopes knowledge to a single worker (QIK-315). Pass the worker id from the worker/studio
// pages so a worker only ever ingests/lists/deletes/retrieves its own documents.
export const ingest = (doc_id: string, text: string, agentId?: string) =>
  request<{ doc_id: string; chunks: number }>("/knowledge/ingest", {
    method: "POST",
    body: JSON.stringify(agentId ? { doc_id, text, agent_id: agentId } : { doc_id, text }),
  });
export const listDocuments = (agentId?: string) =>
  request<Doc[]>(`/knowledge/documents${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ""}`);
export const deleteDocument = (docId: string, agentId?: string) =>
  request<{ removed: number }>(
    `/knowledge/documents/${encodeURIComponent(docId)}${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ""}`,
    { method: "DELETE" });
export const ask = (conversation_id: string, question: string, agent_id: string) =>
  request<{ role: string; text: string }>("/chat/ask", {
    method: "POST",
    body: JSON.stringify({ conversation_id, question, agent_id }),
  });

// Intelligence Worker
export type IntelligenceReply = {
  reply: string;
  intent: string;
  conversation_id: string;
  sources: string[];
  passages_used: number;
};
export const askIntelligence = (conversation_id: string, question: string, agent_id: string) =>
  request<IntelligenceReply>(`/intelligence/agents/${encodeURIComponent(agent_id)}/chat/ask`, {
    method: "POST",
    body: JSON.stringify({ conversation_id, question }),
  });
export const getIntelligenceChatHistory = (agent_id: string, conversation_id: string) =>
  request<{ role: string; text: string }[]>(`/intelligence/agents/${encodeURIComponent(agent_id)}/chat/${encodeURIComponent(conversation_id)}/history`);
export type Discrepancy = {
  class: string;
  class_label: string;
  severity: "high" | "medium" | "low";
  ref: string | null;
  title: string;
  summary: string;
  claimed_at: string | null;
  evidence_at: string | null;
  sources: { source: string; source_label: string; external_id: string; url: string | null; actor: string; occurred_at: string | null }[];
};
export const getDiscrepancies = (agentId: string) => request<Discrepancy[]>(`/intelligence/agents/${encodeURIComponent(agentId)}/discrepancies`);

export type Distribution = { count: number; medianHours: number; p85Hours: number; minHours: number; maxHours: number } | null;
export type SprintMetrics = {
  number: number;
  name: string;
  state: string;
  committed: { tickets: number; points: number };
  done: { tickets: number; points: number };
  projectedCarryOver: { tickets: number; points: number };
} | null;
export type ProjectMetrics = {
  available: boolean;
  error?: string;
  window: { key: string; from: string; to: string };
  throughput: { tickets: number; points: number; unestimated: number; ticketsPerWeek: number | null; pointsPerWeek: number | null; completeWeeks: number };
  cycleTime: { hours: Distribution; inFlight: number; deliveredWithoutStart: number; abandoned: number };
  leadTime: { hours: Distribution; ticketsShipped: number; ticketsWithoutLeadTime: number; deploys: number; deploysPerWeek: number | null; lastDeployAt: string | null };
  wip: { total: number; points: number; blocked: number; byStatus: { status: string; count: number; points: number }[]; medianInFlightHours: number | null; oldest: { ticketKey: string; inFlightHours: number } | null };
  review: { openCount: number; oldestOpen: { ticketKey: string; hours: number } | null; hours: Distribution };
  blocked: { openSpells: number; oldestOpenHours: number | null; ticketsAffected: number; reasons: { reason: string | null; spells: number; tickets: number; hours: number }[] };
  sprint?: SprintMetrics;
};
export type IntelligenceMetrics = { projects: Record<string, ProjectMetrics> };
export const getIntelligenceMetrics = (agentId: string) => request<IntelligenceMetrics>(`/intelligence/agents/${encodeURIComponent(agentId)}/metrics`);

// Research briefs
export type FindingOut = {
  text: string;
  confidence: number | null;
  evidence_refs: string[];
  gaps: string;
};
export type BriefOut = {
  status: "in_progress" | "draft" | "accepted";
  summary: string;
  findings: FindingOut[];
  gaps: string;
  citations: string[];
  accepted_at: string | null;
};
export type ResearchRunOut = {
  run_id: string;
  tenant: string;
  agent_id: string;
  subject: string;
  facets: string[];
  status: Record<string, unknown>;
  verdict: string | null;
  cost: Record<string, unknown> | null;
  brief: BriefOut | null;
};
export const createResearchRun = (agentId: string, body: { subject: string; facets: string[] }) =>
  request<ResearchRunOut>(`/intelligence/agents/${encodeURIComponent(agentId)}/research/runs`, { method: "POST", body: JSON.stringify(body) });
export const getResearchRun = (agentId: string, runId: string) =>
  request<ResearchRunOut>(`/intelligence/agents/${encodeURIComponent(agentId)}/research/runs/${encodeURIComponent(runId)}`);
export const acceptResearchRun = (agentId: string, runId: string) =>
  request<ResearchRunOut>(`/intelligence/agents/${encodeURIComponent(agentId)}/research/runs/${encodeURIComponent(runId)}/accept`, { method: "POST" });

// Backlog proposals from research
export type ProposedTicket = {
  title: string;
  description_md: string;
  type: "FEATURE" | "BUG" | "CHORE" | "SPIKE" | "FINDING" | "EPIC";
  priority: "URGENT" | "HIGH" | "MEDIUM" | "LOW" | "NONE";
  estimate_points: number | null;
  parent_index: number | null;
  finding_index: number | null;
  evidence_refs: string[];
};
export type BacklogProposal = {
  project_key: string;
  items: ProposedTicket[];
};
export type BacklogCreateResult = { created: { index: number; key: string; title: string }[] };
export const getBacklogProposal = (agentId: string, runId: string) =>
  request<BacklogProposal>(`/intelligence/agents/${encodeURIComponent(agentId)}/research/runs/${encodeURIComponent(runId)}/backlog`);
export const createBacklogTickets = (agentId: string, runId: string, body: BacklogProposal) =>
  request<BacklogCreateResult>(`/intelligence/agents/${encodeURIComponent(agentId)}/research/runs/${encodeURIComponent(runId)}/backlog`, { method: "POST", body: JSON.stringify(body) });

// Grounded batch answering (confidence + citations + human-review gate) + xlsx export
export type BatchAnswer = { id: string; question: string; answer: string; confidence: number; decision: string; citations: string[] };
export const batchAnswer = (questions: string[], agent_id: string) =>
  request<BatchAnswer[]>("/agents/batch-answer", { method: "POST", body: JSON.stringify({ questions, agent_id }) });
export async function batchExportUrl(questions: string[], agent_id: string): Promise<string> {
  const blob = await requestBlob("/agents/batch-export", {
    method: "POST",
    body: JSON.stringify({ questions, agent_id }),
  });
  return URL.createObjectURL(blob);
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

// Team Access (Settings > Team): the tenant's users with roles, plus pending invites.
// Backend Role enum <-> stage labels: viewer=User, editor=Creator, admin=Admin, owner=Owner.
// Only viewer/editor/admin are assignable; owner is a protected account owner.
export type TenantRole = "viewer" | "editor" | "admin" | "owner";
export const ASSIGNABLE_ROLES: { value: Exclude<TenantRole, "owner">; label: string }[] = [
  { value: "viewer", label: "User" },
  { value: "editor", label: "Creator" },
  { value: "admin", label: "Admin" },
];
export const ROLE_LABELS: Record<TenantRole, string> = {
  viewer: "User", editor: "Creator", admin: "Admin", owner: "Owner",
};
export type TenantUser = {
  id: string; email: string; name: string; role: TenantRole; role_label: string;
  status: "accepted"; is_owner: boolean;
};
export type PendingInvite = {
  email: string; role: TenantRole; role_label: string; status: "pending"; invited_at: number;
};
export type TenantUsers = { users: TenantUser[]; pending: PendingInvite[] };
export const listTenantUsers = () => request<TenantUsers>("/identity/users");
export const inviteUser = (email: string, role: Exclude<TenantRole, "owner">) =>
  request<PendingInvite>("/identity/users/invite", { method: "POST", body: JSON.stringify({ email, role }) });
export const updateUserRole = (userId: string, role: Exclude<TenantRole, "owner">) =>
  request<TenantUser>(`/identity/users/${encodeURIComponent(userId)}/role`, { method: "PUT", body: JSON.stringify({ role }) });
export const removeUser = (userId: string) =>
  request<{ removed: string }>(`/identity/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
export const cancelInvite = (email: string) =>
  request<{ removed: string }>(`/identity/users/pending/${encodeURIComponent(email)}`, { method: "DELETE" });

// RFP packs (tenders a worker is answering) + section assignments
/** One source document a tender was parsed from (rfp.service.RfpPack.source_documents). */
export type SourceDocument = { name: string; chars: number; uploaded_at: string };
export type RfpPack = {
  id: string; tenant: string; agent_id: string; title: string; client_name: string; deadline: string | null;
  stage: string; created_at: string;
  source_documents?: SourceDocument[];
  outcome: "won" | "lost" | "withdrawn" | null; outcome_reason: string; outcome_value: number | null; outcome_at: string | null;
  gen_status?: TenderGenStatus | null;
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
// Answer-development chat: grounded in the company knowledge base AND the tender context, so it can
// expand draft answers from company documents, not only answer questions about the tender document.
export const askTenderChat = (packId: string, question: string) =>
  request<{ question: string; answer: string; sources: string[] }>(`/rfp/packs/${packId}/chat`, {
    method: "POST", body: JSON.stringify({ question }),
  });
// Persisted per-tender cockpit chat: reload the stored conversation (in order) so closing,
// refreshing, or logging back in restores the prior exchange for this tender.
export const getTenderChatHistory = (packId: string) =>
  request<{ role: string; text: string }[]>(`/rfp/packs/${packId}/chat/history`);

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
  if (!res.ok) throw new ApiError(res.status, extractDetail(await res.text()));
  return res.json() as Promise<T>;
}
// GET reads the persisted brief/compliance (no LLM). Returns null when nothing has been generated
// yet, so tabs can distinguish "not generated" from "generating" (via /status) without re-parsing.
export const getBrief = (packId: string) =>
  request<TenderBrief | null>(`/rfp/packs/${packId}/brief`);
export const getCompliance = (packId: string) =>
  request<ComplianceItem[] | null>(`/rfp/packs/${packId}/compliance`);
// POST re-parses the tender document (regenerate). Only invoked from an explicit action now.
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
  word_limit: number | null; ai_answer: string; ai_sources: string[];
  // Two distinct grounding metrics (0..1): `confidence` is the model's real self-report and
  // `grounding` is the critic's independent score. `gaps` is a human-input prompt ("" if none).
  confidence: number; grounding: number; gaps: string;
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

/** One node of GET /sections: a section plus its nested questions and their averaged confidence.
 * A top-level section also carries rolled-up grounding metrics from its sub-sections: `kb_gap`
 * (any descendant is a KB gap), `confidence`/`grounding` (avg across drafted descendants, null if
 * none drafted), and `subsection_count` (number of child sub-sections). */
export type PackSectionNode = PackSection & {
  questions: PackQuestion[]; avg_confidence: number;
  confidence: number | null; grounding: number | null; subsection_count: number;
};

export type PackOverview = {
  sections: number; subsections: number; sections_locked: number; questions: number;
  ai_drafted: number; ai_drafted_total: number; for_human_review: number;
  kb_sources: number; kb_gaps: number; avg_confidence: number; avg_grounding: number;
  can_finalize: boolean;
};

export const getPackOverview = (packId: string) =>
  request<PackOverview>(`/rfp/packs/${packId}/overview`);

export const setPackStage = (packId: string, stage: PackStage) =>
  request<RfpPack>(`/rfp/packs/${packId}/stage`, { method: "PUT", body: JSON.stringify({ stage }) });

// ── Stepper (Upload -> Parsed -> Assigned -> Drafting -> Review) ─────────────
// The tender-generation background job's per-artifact progress. The Sections tab polls
// GET /status (~3s) while anything is pending/running and derives the stepper state from it.
export type GenState = "pending" | "running" | "ready" | "partial" | "error";
export type TenderGenStatus = {
  requirements?: GenState;
  sections?: GenState;
  brief?: GenState;
  compliance?: GenState;
  drafts?: { state: GenState; done: number; total: number; failed?: number };
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

// ── Section assignments (collaboration) ──────────────────────────────────────
// Assign RFP pack sections (or standalone questions) to tenant members, track completion, and roll
// it up into a per-member dashboard. Backed by qiko-core app.modules.assignments (prefix
// /assignments). Mutations (bulk/reassign/delete/reminder) require Admin+; a status toggle is
// allowed for the assignee or an owner/admin.
export type AssignmentStatus = "pending" | "completed";
export type Assignment = {
  id: string; pack_id: string; agent_id: string; assignee_user_id: string;
  assigned_by_user_id: string; question: string; section_id: string | null;
  section_title: string | null; rfp_title: string | null; status: AssignmentStatus;
  due_at: string | null; completed_at: string | null; created_at?: string | null;
};

/** One member's rollup for a pack (GET /assignments/dashboard). */
export type AssignmentDashboardRow = {
  user_id: string; assigned: number; completed: number; pending: number;
  progress: number; status: "overdue" | "pending" | "completed";
  sections: { section_id: string; section_title: string | null; rfp_title: string | null; due_at: string | null }[];
};

/** A section to assign in bulk: every listed question becomes one Assignment for the assignee. */
export type SectionAssignInput = {
  section_id: string; assignee_user_id: string; questions: string[];
  title?: string | null; due_at?: string | null;
};
/** A standalone question to assign in bulk (not tied to a section). */
export type QuestionAssignInput = { assignee_user_id: string; question: string; due_at?: string | null };

export const bulkAssign = (body: {
  pack_id: string; agent_id: string; rfp_title?: string | null;
  sections?: SectionAssignInput[]; questions?: QuestionAssignInput[];
}) => request<Assignment[]>("/assignments/bulk", { method: "POST", body: JSON.stringify(body) });

export const listAssignments = (params: { pack_id?: string; assignee_user_id?: string; status?: AssignmentStatus } = {}) => {
  const q = new URLSearchParams();
  if (params.pack_id) q.set("pack_id", params.pack_id);
  if (params.assignee_user_id) q.set("assignee_user_id", params.assignee_user_id);
  if (params.status) q.set("status", params.status);
  const qs = q.toString();
  return request<Assignment[]>(`/assignments${qs ? `?${qs}` : ""}`);
};

export const assignmentsDashboard = (packId: string, memberUserIds: string[]) =>
  request<AssignmentDashboardRow[]>(
    `/assignments/dashboard?pack_id=${encodeURIComponent(packId)}&member_user_ids=${encodeURIComponent(memberUserIds.join(","))}`,
  );

export const updateAssignmentStatus = (assignmentId: string, status: AssignmentStatus) =>
  request<Assignment>(`/assignments/${assignmentId}/status`, { method: "PUT", body: JSON.stringify({ status }) });

export const reassignAssignment = (assignmentId: string, patch: { assignee_user_id?: string; question?: string; due_at?: string | null }) =>
  request<Assignment>(`/assignments/${assignmentId}`, { method: "PUT", body: JSON.stringify(patch) });

export const deleteSectionAssignments = (packId: string, sectionId: string) =>
  request<{ section_id: string; deleted_count: number }>(`/assignments/section/${packId}/${sectionId}`, { method: "DELETE" });

export const deletePackAssignments = (packId: string) =>
  request<{ pack_id: string; deleted_count: number }>(`/assignments/pack/${packId}`, { method: "DELETE" });

export const sendAssignmentReminder = (body: { pack_id: string; assignee_user_id?: string; assignee_email?: string }) =>
  request<{ reminders_sent: number; reminders_failed: number; reason?: string }>(
    "/assignments/send-reminder", { method: "POST", body: JSON.stringify(body) },
  );

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

/** Upload one OR MANY RFP/tender documents to a pack: extracts requirements and (re)builds the
 * section tree. Every file is sent under the `files` field, so a single file works too. */
export async function extractPack(packId: string, files: File | File[]): Promise<PackRequirement[]> {
  const csrf = csrfToken();
  const form = new FormData();
  for (const f of Array.isArray(files) ? files : [files]) form.append("files", f);
  const res = await fetch(`${BASE}/rfp/packs/${packId}/extract`, {
    method: "POST", credentials: "include", body: form,
    headers: csrf ? { "x-csrf-token": csrf } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, extractDetail(await res.text()));
  return res.json();
}

/** Fetch an export (xlsx / clean docx / annotated review docx) as a Blob for client-side download. */
export async function exportPackBlob(packId: string, kind: "xlsx" | "docx-clean" | "docx-review"): Promise<Blob> {
  return requestBlob(`/rfp/packs/${packId}/export/${kind}`);
}

export async function ingestFile(docId: string, file: File, agentId?: string): Promise<{ chunks: number }> {
  const csrf = document.cookie.match(/(?:^|; )qiko_csrf=([^;]+)/)?.[1];
  const form = new FormData();
  form.append("file", file);
  form.append("doc_id", docId);
  if (agentId) form.append("agent_id", agentId);
  const res = await fetch(`${BASE}/knowledge/ingest-file`, {
    method: "POST", credentials: "include", body: form,
    headers: csrf ? { "x-csrf-token": csrf } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, extractDetail(await res.text()));
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
  id: number; agentId: string; sourceKey: string; name: string; type: string;
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
    noticeType: string | null; links?: { url: string; description?: string | null }[];
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
// Per-source scheduled scan cadence (mirrors the backend SCAN_CADENCES enum). "manual" turns off
// auto-scanning; the operator runs the source on demand via the scan endpoints.
export type SalesScanCadence = "minutely" | "hourly" | "daily" | "weekly" | "manual";
// PATCH accepts either the on/off status or the scan cadence (or both) -- at least one is required.
// sourceKey is any attached key (built-in ted/ungm or a custom source added from the catalog).
export const updateSalesSource = (
  agentId: string, sourceKey: string, body: { status?: string; scan_cadence?: SalesScanCadence },
) =>
  request<{ source: SalesIntelSource }>(`/sales-intelligence/${agentId}/sources/${sourceKey}`, {
    method: "PATCH", body: JSON.stringify(body),
  });
export const scanTedSource = (agentId: string, body: Record<string, unknown> = {}) =>
  request<{ scanned: boolean; found: number }>(`/sales-intelligence/${agentId}/scan/ted`, {
    method: "POST", body: JSON.stringify(body),
  });
export const scanUngmSource = (agentId: string, body: Record<string, unknown> = {}) =>
  request<{ scanned: boolean; found: number }>(`/sales-intelligence/${agentId}/scan/ungm`, {
    method: "POST", body: JSON.stringify(body),
  });
// Generic scan by source key (built-in routes /scan/ted + /scan/ungm still take precedence server-side).
export const scanSalesSource = (agentId: string, sourceKey: string, body: Record<string, unknown> = {}) =>
  request(`/sales-intelligence/${agentId}/scan/${sourceKey}`, { method: "POST", body: JSON.stringify(body) });

// --- Source catalog + custom sources (R2 Leg 5) ---
export type SalesSourceCatalogItem = {
  key: string; name: string; description: string | null; type: string;
  authStatus: string | null; scannable: boolean; alreadyAdded: boolean;
  defaultConfig: { url: string | null; apiUrl: string | null; defaultQuery: string; ingestFilters: unknown };
};
export const getSalesSourcesCatalog = (agentId: string) =>
  request<{ catalog: SalesSourceCatalogItem[] }>(`/sales-intelligence/${agentId}/sources/catalog`);
// Attach a catalog portal (source_key only) or a custom source (name + config.url required).
export const createSalesSource = (agentId: string, body: {
  source_key: string; name?: string; config?: { url?: string; api_url?: string };
}) => request<{ source: SalesIntelSource }>(`/sales-intelligence/${agentId}/sources`, {
  method: "POST", body: JSON.stringify(body),
});
export const deleteSalesSource = (agentId: string, sourceKey: string) =>
  request<{ ok: boolean; sourceKey: string }>(`/sales-intelligence/${agentId}/sources/${sourceKey}`, {
    method: "DELETE",
  });

export type SalesOpportunityFilters = {
  stage?: OpportunityStage; recommendation?: Recommendation; source_key?: string; title?: string;
  search?: string; limit?: number | "all"; assigned_reviewer_user_id?: string;
  include_archived?: boolean; archived_only?: boolean;
};
export const listSalesOpportunities = (agentId: string, filters: SalesOpportunityFilters = {}) =>
  request<{ opportunities: SalesOpportunity[]; summary: Record<string, unknown> }>(
    `/sales-intelligence/${agentId}/opportunities${siQuery(filters)}`,
  );
export const getSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}`);

// Manual "add an opportunity" flow (mirrors the backend CreateOpportunityBody / UpdateOpportunityBody).
// Only `title` is required on create; everything else is optional. The richer descriptive fields are
// persisted server-side in the opportunity's raw payload and surfaced back via `detail`.
export type SalesOpportunityContactInput = { name?: string | null; email?: string | null; phone?: string | null };
export type SalesOpportunityLinkInput = { url?: string | null; description?: string | null };
export type CreateSalesOpportunityInput = {
  title: string;
  buyer?: string | null;
  country?: string | null;
  region?: string | null;
  category?: string | null;
  estimated_value?: number | null;
  currency?: string | null;
  published_at?: string | null;
  deadline_at?: string | null;
  source_url?: string | null;
  source_key?: string | null;
  source_name?: string | null;
  stage?: OpportunityStage;
  run_qualification?: boolean;
  reference?: string | null;
  notice_type?: string | null;
  security_clearance?: string | null;
  extraction_confidence?: number | null;
  framework?: string | null;
  contract_duration?: string | null;
  technology?: string | null;
  contacts?: SalesOpportunityContactInput[];
  links?: SalesOpportunityLinkInput[];
  executive_summary?: string | null;
  risk_summary?: string | null;
  opportunity_summary?: string | null;
  requirements?: string[];
  deliverables?: string[];
  qualification_score?: number | null;
  recommendation?: string | null;
  confidence?: number | null;
  ai_reasoning?: string | null;
  recommendations?: string[];
  notes?: string | null;
};
// The edit form patches the same fields (all optional) plus an opt-in `requalify` re-score.
export type UpdateSalesOpportunityInput = Partial<Omit<CreateSalesOpportunityInput, "title">> & {
  title?: string;
  requalify?: boolean;
};

export const createSalesOpportunity = (agentId: string, payload: CreateSalesOpportunityInput) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities`, {
    method: "POST", body: JSON.stringify(payload),
  });
export const updateSalesOpportunity = (agentId: string, opportunityId: number | string, payload: UpdateSalesOpportunityInput) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}`, {
    method: "PATCH", body: JSON.stringify(payload),
  });
// Stage transition (kanban drag / "Move to..." / "Run Qualification"). The backend validates the
// target against the manual pipeline stages; `pushed` is reached via pushOpportunityToSalesforce.
export const transitionSalesOpportunity = (agentId: string, opportunityId: number | string, stage: OpportunityStage) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/transition`, {
    method: "POST", body: JSON.stringify({ stage }),
  });
export const getSalesOpportunityHistory = (agentId: string, opportunityId: number | string) =>
  request<{ history: SalesActivityLog[] }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/history`);
export const archiveSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/archive`, { method: "POST" });
export const restoreSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ opportunity: SalesOpportunity }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}/restore`, { method: "POST" });
export const deleteSalesOpportunity = (agentId: string, opportunityId: number | string) =>
  request<{ deleted: boolean }>(`/sales-intelligence/${agentId}/opportunities/${opportunityId}`, { method: "DELETE" });

// Salesforce activity action names logged by the backend (connect/disconnect + push lifecycle).
// The salesforce-log page passes these so the table is scoped to Salesforce events only.
export const SALESFORCE_LOG_ACTIONS = [
  "salesforce_connected", "salesforce_disconnected",
  "salesforce_push_started", "salesforce_push_succeeded", "salesforce_push_failed",
] as const;
export const getSalesActivityLogs = (
  agentId: string,
  params: { opportunity_id?: number; page?: number; per_page?: number; actions?: readonly string[] } = {},
) => {
  const { actions, ...rest } = params;
  const q = siQuery(rest);
  const actionsQuery = actions?.length
    ? actions.map((a) => `actions=${encodeURIComponent(a)}`).join("&")
    : "";
  const query = [q.replace(/^\?/, ""), actionsQuery].filter(Boolean).join("&");
  return request<{ logs: SalesActivityLog[]; total: number }>(
    `/sales-intelligence/${agentId}/activity-logs${query ? `?${query}` : ""}`,
  );
};
export const getSalesScanHistory = (agentId: string, params: { source_key?: string; status?: string; limit?: number } = {}) =>
  request<{ history: SalesScanHistoryEntry[] }>(`/sales-intelligence/${agentId}/scan-history${siQuery(params)}`);

export type SalesIngestFilter = {
  agentId: string | null; queryEnabled: boolean; queryKeyword: string;
  allCountries: boolean; allCategories: boolean; updatedAt: string | null;
};
export const getSalesIngestFilter = (agentId: string) =>
  request<SalesIngestFilter>(`/sales-intelligence/${agentId}/ingest-filters`);
export const updateSalesIngestFilter = (agentId: string, body: {
  query_enabled?: boolean; query_keyword?: string; all_countries?: boolean; all_categories?: boolean;
}) => request<SalesIngestFilter>(`/sales-intelligence/${agentId}/ingest-filters`, { method: "PATCH", body: JSON.stringify(body) });

// Canonical review decisions match the backend REVIEW_DECISIONS enum (approved/rejected/
// needs_review); sending "approve"/"reject" here previously 422'd every review.
export type ReviewDecision = "approved" | "rejected" | "needs_review";
export const reviewSalesOpportunity = (agentId: string, opportunityId: number | string, decision: ReviewDecision, notes = "") =>
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

// Agent-level Decision History -- the approve/reject/override audit trail aggregated across ALL
// opportunities for the agent (GET /decision-history), with decision + reviewer filters.
export type SalesDecisionReviewer = { id: string; userName: string | null; email: string | null };
export type SalesDecisionHistoryEntry = SalesDecision & {
  opportunityTitle: string | null; opportunityStage: string | null; reviewer: SalesDecisionReviewer | null;
};
export type SalesDecisionHistorySummary = { approved: number; rejected: number; overrides: number; total: number };
export type SalesDecisionHistoryResponse = {
  decisionHistory: SalesDecisionHistoryEntry[]; reviewers: SalesDecisionReviewer[]; summary: SalesDecisionHistorySummary;
};
export type SalesDecisionFilter = "approved" | "rejected" | "needs_review" | "override" | "all";
export const getSalesDecisionHistory = (
  agentId: string, params: { decision?: SalesDecisionFilter; reviewer_user_id?: string } = {},
) =>
  request<SalesDecisionHistoryResponse>(`/sales-intelligence/${agentId}/decision-history${siQuery(params)}`);

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

// Public chat by worker ID (no auth, no tenant -- resolved server-side). QIK-334.
export type PublicWorker = { id: string; name: string; atype: string };
export const publicWorkerDetail = (workerId: string) =>
  request<PublicWorker>(`/public/worker/${encodeURIComponent(workerId)}`);
export const publicChatById = (workerId: string, question: string, userEmail?: string) =>
  request<{ role: string; text: string }>("/public/chat", {
    method: "POST",
    body: JSON.stringify({ worker_id: workerId, question, ...(userEmail ? { user_email: userEmail } : {}) }),
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
export type BillingPlan = { key: string; id: number; name: string; display_name: string; price_id: string; amount: number; interval: string; display_price: string; worker_limit: number; features: string[] };
export const listPlans = () => request<BillingPlan[]>("/billing/plans");
export const startCheckout = (plan: string, priceId: string) =>
  request<{ url: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ plan, price_id: priceId }) });
export const billingPortal = () => request<{ url: string }>("/billing/portal");
export const cancelSubscription = () =>
  request<Subscription>("/billing/subscription/cancel", { method: "POST" });
export const resumeSubscription = () =>
  request<Subscription>("/billing/subscription/resume", { method: "POST" });

// ── Finance (Financial Analyst) ──────────────────────────────────────────────
// Types are generated from the qiko-core OpenAPI spec via @qiko/api-client.
import type { components, paths } from "@qiko/api-client";

export type FinanceUploadResponse = paths["/api/v1/finance/{agent_id}/upload"]["post"]["responses"][201]["content"]["application/json"];
export type FinanceFilesResponse = paths["/api/v1/finance/{agent_id}/files"]["get"]["responses"][200]["content"]["application/json"];
export type FinanceDeleteResponse = paths["/api/v1/finance/{agent_id}/files"]["delete"]["responses"][200]["content"]["application/json"];
export type FinanceAnalytics = paths["/api/v1/finance/{agent_id}/analytics"]["get"]["responses"][200]["content"]["application/json"];
export type FinanceChatResponse = paths["/api/v1/finance/{agent_id}/chat"]["post"]["responses"][200]["content"]["application/json"];
export type FinanceHistoryResponse = paths["/api/v1/finance/{agent_id}/history"]["get"]["responses"][200]["content"]["application/json"];
export type FinanceClearHistoryResponse = paths["/api/v1/finance/{agent_id}/history"]["delete"]["responses"][200]["content"]["application/json"];

export type FinanceFile = components["schemas"]["FinanceFileRef"];
export type FinanceHistoryItem = components["schemas"]["FinanceHistoryMessage"];
export type FinanceSummary = components["schemas"]["FinanceSummaryOut"];
export type FinanceExpenseCategory = components["schemas"]["FinanceExpenseCategory"];
export type FinanceTopVendor = components["schemas"]["FinanceTopVendor"];
export type FinanceMonthlyTrend = components["schemas"]["FinanceMonthlyTrend"];
export type FinanceUnitExpense = components["schemas"]["FinanceUnitExpense"];
export type FinanceUnitLedger = components["schemas"]["FinanceUnitLedger"];
export type FinanceProperty = components["schemas"]["FinancePropertyOut"];
export type FinanceChartVendor = components["schemas"]["FinanceChartVendor"];
export type FinanceChartIncomeExpense = components["schemas"]["FinanceChartIncomeExpense"];
export type FinanceCharts = components["schemas"]["FinanceChartsOut"];
export type FinanceTrendSection = components["schemas"]["FinanceTrendSectionOut"];
export type FinanceTrends = FinanceTrendSection[];

export const getFinanceAnalytics = (agentId: string, query: { from?: string; to?: string; month?: string } = {}) => {
  const q = new URLSearchParams();
  if (query.from) q.set("from", query.from);
  if (query.to) q.set("to", query.to);
  if (query.month) q.set("month", query.month);
  const s = q.toString();
  return request<FinanceAnalytics>(`/finance/${agentId}/analytics${s ? `?${s}` : ""}`);
};

export const listFinanceFiles = (agentId: string) => request<FinanceFilesResponse>(`/finance/${agentId}/files`);

export const deleteFinanceFiles = (agentId: string, ids: string[]) =>
  request<FinanceDeleteResponse>(`/finance/${agentId}/files`, {
    method: "DELETE", body: JSON.stringify({ ids }),
  });

export async function uploadFinanceFile(agentId: string, file: File): Promise<FinanceUploadResponse> {
  const csrf = csrfToken();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/finance/${agentId}/upload`, {
    method: "POST", credentials: "include", body: form,
    headers: csrf ? { "x-csrf-token": csrf } : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, extractDetail(await res.text()));
  return res.json();
}

export const financeChat = (agentId: string, message: string) =>
  request<FinanceChatResponse>(`/finance/${agentId}/chat`, { method: "POST", body: JSON.stringify({ message }) });

export const getFinanceHistory = (agentId: string, limit = 100) =>
  request<FinanceHistoryResponse>(`/finance/${agentId}/history?limit=${limit}`);

export const clearFinanceHistory = (agentId: string) =>
  request<FinanceClearHistoryResponse>(`/finance/${agentId}/history`, { method: "DELETE" });

// Intelligence Worker sources (Slack capture, GitHub, Qiko Track).
export type IntelligenceSource = { key: string; name: string; description: string; pollable: boolean; connected: boolean };
export type IntelligenceSourceConnection =
  | { key: "github"; connected: boolean; token_masked: string; repo_allowlist: string[]; watched_branches: string[] }
  | { key: "qiko_track"; connected: boolean; service_token_used?: boolean; token_masked: string; project_keys: string[]; base_url: string }
  | { key: "slack"; connected: boolean; team_id: string | null; watched_channels: string[]; channels: { id: string; name: string }[] };

export type QikoTrackPreview = {
  service_token_configured: boolean;
  suggested?: { key: string; name: string; kind: "PRODUCT" | "CLIENT" | "INTERNAL" };
  existing_projects: { key: string; name: string; kind: "PRODUCT" | "CLIENT" | "INTERNAL" }[];
};

export const listIntelligenceSources = (agentId: string) =>
  request<IntelligenceSource[]>(`/intelligence/agents/${agentId}/sources`);

export const getIntelligenceSource = (agentId: string, sourceKey: string) =>
  request<IntelligenceSource>(`/intelligence/agents/${agentId}/sources/${sourceKey}`);

export const getIntelligenceSourceConnection = (agentId: string, sourceKey: string) =>
  request<IntelligenceSourceConnection>(`/intelligence/agents/${agentId}/sources/${sourceKey}/connection`);

export const getIntelligenceQikoTrackPreview = (agentId: string) =>
  request<QikoTrackPreview>(`/intelligence/agents/${agentId}/sources/qiko_track/preview`);

export const getGitHubAppInstallUrl = (agentId: string) =>
  request<{ url: string }>(`/intelligence/agents/${agentId}/sources/github/install`);

export const connectIntelligenceSource = (agentId: string, sourceKey: string, body: Record<string, unknown> = {}) =>
  request<{ connected: boolean; url?: string; state?: string }>(`/intelligence/agents/${agentId}/sources/${sourceKey}`, {
    method: "POST", body: JSON.stringify(body),
  });

export const disconnectIntelligenceSource = (agentId: string, sourceKey: string) =>
  request<{ disconnected: boolean }>(`/intelligence/agents/${agentId}/sources/${sourceKey}`, { method: "DELETE" });

export const verifyIntelligenceSource = (agentId: string, sourceKey: string, body: Record<string, unknown>) =>
  request<{ ok: boolean; error?: string; team?: string; user?: string; repos?: { full_name: string; private: boolean }[] }>(
    `/intelligence/agents/${agentId}/sources/${sourceKey}/verify`, { method: "POST", body: JSON.stringify(body) });

export const testIntelligenceSource = (agentId: string, sourceKey: string) =>
  request<{ ok: boolean; error?: string; team?: string; user?: string; repos?: { full_name: string; private: boolean }[] }>(
    `/intelligence/agents/${agentId}/sources/${sourceKey}/test`, { method: "POST" });

export const setSlackWatchedChannels = (agentId: string, channelIds: string[]) =>
  request<{ watched_channels: string[] }>(`/intelligence/agents/${agentId}/sources/slack/channels`, {
    method: "POST", body: JSON.stringify({ channel_ids: channelIds }),
  });

export const listSlackWatchedChannels = (agentId: string) =>
  request<{ watched_channels: string[]; channels: { id: string; name: string }[] }>(`/intelligence/agents/${agentId}/sources/slack/channels`);

// Intelligence Worker documents (uploaded files ingested as evidence)
export type IntelligenceDocument = {
  doc_id: string;
  filename: string;
  content_type: string;
  size: number;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};
export const listIntelligenceDocuments = (agentId: string) =>
  request<IntelligenceDocument[]>(`/intelligence/agents/${agentId}/documents`);
export const uploadIntelligenceDocument = (agentId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<IntelligenceDocument>(`/intelligence/agents/${agentId}/documents`, { method: "POST", body: form });
};
export const deleteIntelligenceDocument = (agentId: string, docId: string) =>
  request<{ deleted: boolean }>(`/intelligence/agents/${agentId}/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
