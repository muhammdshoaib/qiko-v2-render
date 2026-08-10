// Admin API client for qiko-core /api/v1 (cookie auth, credentials included).
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

let refreshInFlight: Promise<boolean> | null = null;
function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const csrf = csrfToken();
        const response = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrf-token": csrf } : {}) },
        });
        return response.ok;
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
  return fetch(`${BASE}${path}`, {
    credentials: "include",
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "x-csrf-token": csrf } : {}),
      ...(opts.headers ?? {}),
    },
  });
}

const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout"];

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  let response = await doFetch(path, opts);
  if (response.status === 401 && !NO_REFRESH_PATHS.some((candidate) => path.startsWith(candidate))) {
    if (await refreshSession()) {
      response = await doFetch(path, opts);
    } else if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
  }
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return response.status === 204 ? (null as T) : ((await response.json()) as T);
}

export const login = (email: string, password: string, totp?: string) =>
  request("/auth/login", { method: "POST", body: JSON.stringify({ email, password, totp: totp || null }) });
export const logout = () => request("/auth/logout", { method: "POST" });
export const authMe = () => request<{ user: { id: string; email: string; role: string; twofa_enabled: boolean } }>("/auth/me");
export const forgotPassword = (email: string) =>
  request("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });

/** A sort the SERVER understands. The key is validated against a per-endpoint allowlist and an unknown
 *  one is a 422, not a silent fallback, so this type exists to keep the client honest about which keys
 *  each directory actually offers. */
export type ListSort = { sort: string; order: "asc" | "desc" };

const applySort = (params: URLSearchParams, sort?: ListSort) => {
  if (!sort) return;
  params.set("sort", sort.sort);
  params.set("order", sort.order);
};

export type Customer = { user_id: string; email: string; plan: string; earnings_cents: number };
export const listCustomers = (search = "", page = 1, sort?: ListSort, plan?: string) => {
  const params = new URLSearchParams({ page: String(page) });
  if (search) params.set("search", search);
  // The endpoint has always accepted plan and no page sent it, so "who is still on free" could only be
  // answered by paging through everything.
  if (plan) params.set("plan", plan);
  applySort(params, sort);
  return request<{ total: number; page: number; page_size?: number; items: Customer[] }>(
    `/admin/customers?${params}`);
};

export type AdminRole = "viewer" | "super_admin";
export type AdminWorker = {
  id: string; name: string; type: string; status: string; enabled: boolean;
  created_at: string; config: Record<string, string | boolean | number>;
};
export type WorkerAudit = {
  id: number; agent_id: string; changed_by_email: string; previous_enabled: boolean;
  enabled: boolean; reason: string | null; created_at: string;
};
export type CustomerDetail = Customer & {
  is_studio: boolean; deleted: boolean; workers: AdminWorker[]; worker_state_audit: WorkerAudit[];
};
// Only the capabilities the server actually enforces today. view_ai_cost, set_cost_caps and
// view_system_stats arrive with the endpoints they gate, so the UI never offers a permission that
// does nothing.
export type Capability = "view_audit" | "view_customers" | "manage_customers" | "manage_workers" | "manage_billing" | "manage_admins" | "view_ai_cost" | "view_system_stats" | "set_cost_caps";

/** Every capability the backend enforces. This list being short is not cosmetic: the grant form
 *  renders checkboxes from it and posts the SELECTED set, so anything missing here cannot be granted
 *  at all, and saving an explicit set for an existing admin silently strips it. view_audit was added
 *  to the backend without this list, so for one release no operator could grant audit access and
 *  editing a super_admin through this form removed theirs. */
export const ALL_CAPABILITIES: Capability[] = ["view_audit", "view_customers", "manage_customers", "manage_workers", "manage_billing", "manage_admins", "view_ai_cost", "view_system_stats", "set_cost_caps"];

export type PlatformAdmin = { email: string; role: AdminRole; capabilities: Capability[] };
export type AdminGrantAudit = {
  id: number | null; email: string; changed_by_email: string;
  previous_role: AdminRole | null; role: AdminRole | null;
  previous_capabilities: Capability[] | null; capabilities: Capability[] | null;
  reason: string | null; created_at: string;
};

export type TenantRow = {
  tenant_id: string; email: string; plan: string; earnings_cents: number;
  user_count: number; worker_count: number; is_studio: boolean;
};
export type UserRow = {
  id: string; email: string; name: string | null; tenant_id: string | null;
  role: string; role_label: string; twofa_enabled: boolean;
  // is_platform_admin is visible to any platform admin; the role and capability set only to a
  // manage_admins holder, so both are nullable/empty by design rather than by accident.
  is_platform_admin: boolean;
  platform_role: AdminRole | null; platform_capabilities: Capability[];
};
export type WorkerRow = AdminWorker & { tenant_id: string };

type Paged<T> = { total: number; page: number; items: T[] };

const paged = (page: number, extra: Record<string, string | undefined> = {}, sort?: ListSort) => {
  const params = new URLSearchParams({ page: String(page) });
  for (const [key, value] of Object.entries(extra)) if (value) params.set(key, value);
  applySort(params, sort);
  return params;
};

/** The sortable keys each directory declares, mirroring app/modules/admin/sorting.py. Kept here so a
 *  column cannot be marked sortable in the UI without the server agreeing, which would show the
 *  operator a control that returns a 422. */
export const SORTABLE = {
  customers: ["email", "plan", "earnings"],
  // The same endpoint, so the same allowlist. Listed separately because the test resolves the key from
  // the page's directory name.
  subscriptions: ["email", "plan", "earnings"],
  tenants: ["email", "plan", "earnings", "users", "workers"],
  users: ["email", "name", "tenant", "role", "twofa"],
  workers: ["name", "tenant", "status", "enabled", "created"],
  monitoring: ["name", "tenant", "calls", "status", "enabled", "last_seen"],
} as const;

export const listTenants = (search = "", page = 1, sort?: ListSort) =>
  request<Paged<TenantRow>>(`/admin/tenants?${paged(page, { search }, sort)}`);
export const listUsers = (search = "", page = 1, tenantId?: string, sort?: ListSort,
                          extra?: { role?: string; twofa?: string }) =>
  request<Paged<UserRow>>(
    `/admin/users?${paged(page, { search, tenant_id: tenantId, ...extra }, sort)}`);
export const listWorkers = (search = "", page = 1, enabled?: boolean, sort?: ListSort,
                            status?: string) =>
  request<Paged<WorkerRow>>(
    `/admin/workers?${paged(page, {
      search, status,
      enabled: enabled === undefined ? undefined : String(enabled),
    }, sort)}`);

export type UsageTotals = {
  calls: number; input_tokens: number; output_tokens: number;
  cost_nano_usd: number; unpriced_calls: number;
};
export type AiCost = {
  window_days: number; totals: UsageTotals;
  tenant: Record<string, UsageTotals>; model: Record<string, UsageTotals>;
  operation: Record<string, UsageTotals>; day: Record<string, UsageTotals>;
};
export const aiCost = (days = 30) => request<AiCost>(`/admin/ai-cost?days=${days}`);

export type MonitoredWorker = {
  tenant_id: string; id: string; name: string; status: string; enabled: boolean;
  created_at: string; calls: number; last_seen: string | null;
  // Only present for a caller holding view_ai_cost, see cost_visible.
  cost_nano_usd?: number; input_tokens?: number; output_tokens?: number;
};
export const workerMonitoring = (days = 30, page = 1, tenantId?: string, sort?: ListSort,
                                 search?: string, enabled?: boolean) =>
  request<{ total: number; page: number; page_size?: number; window_days: number;
            cost_visible: boolean; items: MonitoredWorker[] }>(
    `/admin/worker-monitoring?${paged(page, {
      days: String(days), tenant_id: tenantId, search,
      enabled: enabled === undefined ? undefined : String(enabled),
    }, sort)}`);

/** Cents to a human string. USD because that is what Stripe is charged in
 * (qiko-core/app/integrations/clients.py:57 sends currency "usd"), and because the tenants page used
 * to render the same earnings_cents figure as GBP while customers hardcoded a "$" prefix. Three
 * spellings of one number is a bug that a right-aligned money column makes obvious. */
export const formatMoney = (cents: number) =>
  (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });

/** nano-USD to a human string. Values are integers on purpose, see the pricing module. */
export const formatUsd = (nanoUsd: number) =>
  (nanoUsd / 1_000_000_000).toLocaleString(undefined, { style: "currency", currency: "USD",
    minimumFractionDigits: 2, maximumFractionDigits: nanoUsd < 10_000_000 ? 6 : 2 });

export type SystemCheck = { name: string; ok: boolean; detail: string | null; latency_ms: number | null };
export type SystemStats = {
  ready: boolean;
  checks: SystemCheck[];
  process: {
    uptime_seconds: number; started_at: string; pid: number; python: string; platform: string;
    max_rss_kb: number; cpu_user_seconds: number; cpu_system_seconds: number;
    load_average: number[] | null; cpu_count: number | null;
  };
  // Each section degrades to available:false with a reason rather than failing the dashboard.
  database: { available: boolean; reason?: string; size_bytes?: number;
    connections_total?: number; connections_active?: number; connections_limit?: number };
  redis: { available: boolean; reason?: string; used_memory_bytes?: number; max_memory_bytes?: number;
    connected_clients?: number; evicted_keys?: number; rejected_connections?: number; uptime_seconds?: number };
  queue: { available: boolean; reason?: string; queue?: string; depth?: number };
  environment: string;
  version: string;
};
export const systemStats = () => request<SystemStats>("/admin/system");

export const formatBytes = (bytes: number) => {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
};

export type CostCap = {
  tenant_id: string; agent_id: string | null; monthly_cap_nano_usd: number;
  unlimited: boolean; alert_threshold_pct: number;
  updated_by_email: string | null; updated_at: string;
};
export const listCostCaps = () =>
  request<{ platform_key: string; items: CostCap[] }>("/admin/cost-caps");
export const setCostCap = (tenantId: string, body: { monthly_cap_usd: number; alert_threshold_pct?: number }, agentId?: string) =>
  request<CostCap>(`/admin/cost-caps/${encodeURIComponent(tenantId)}${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ""}`,
    { method: "PUT", body: JSON.stringify(body) });
export const deleteCostCap = (tenantId: string, agentId?: string) =>
  request<{ removed: string }>(
    `/admin/cost-caps/${encodeURIComponent(tenantId)}${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ""}`,
    { method: "DELETE" });

export const adminMe = () =>
  request<{ role: AdminRole; capabilities: Capability[] }>("/admin/me");
export const listPlatformAdmins = () =>
  request<{ admins: PlatformAdmin[] }>("/admin/org");
export const grantPlatformAdmin = (
  email: string,
  body: { role: AdminRole; capabilities: Capability[] | null; reason?: string },
) => request<PlatformAdmin>(`/admin/org/${encodeURIComponent(email)}`, {
  method: "PUT", body: JSON.stringify(body),
});
// The server accepts limit 1..200 and defaults to 50. Not passing it capped the access log at 50 with
// no indication, so an operator reviewing who changed what silently saw a truncated history.
export const listPlatformAdminAudit = (limit = 200) =>
  request<{ entries: AdminGrantAudit[] }>(`/admin/org/audit?limit=${limit}`);
export const adminRoleOf = (email: string) => request<{ email: string; role: AdminRole | null }>(`/admin/org/role/${encodeURIComponent(email)}`);
export const removePlatformAdmin = (email: string, reason?: string) => {
  // The reason lands in the audit trail; a UI-originated revoke used to record none.
  const query = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return request<{ removed: string }>(`/admin/org/${encodeURIComponent(email)}${query}`, { method: "DELETE" });
};
export const customerDetail = (userId: string) => request<CustomerDetail>(`/admin/customers/${encodeURIComponent(userId)}`);
export const setCustomerStudio = (customerId: string, enabled: boolean) =>
  request<CustomerDetail>(`/admin/customers/${encodeURIComponent(customerId)}/studio`, {
    method: "POST", body: JSON.stringify({ enabled }),
  });
export const setWorkerEnabled = (customerId: string, workerId: string, enabled: boolean, reason: string) =>
  request<AdminWorker>(`/admin/customers/${encodeURIComponent(customerId)}/workers/${encodeURIComponent(workerId)}/enabled`, {
    method: "PATCH", body: JSON.stringify({ enabled, reason: reason.trim() || null }),
  });

export type Overview = { customers_total: number; active_subscriptions: number; by_plan: Record<string, number> };
export const overview = () => request<Overview>("/admin/overview");

export type Analytics = {
  sessions: number;
  active_users: number;
  top_pages: { pagePath: string; sessions: number }[];
  had_data: boolean;
};
export const analytics = () => request<Analytics>("/admin/analytics");

export type Invoice = { stripe_invoice_id: string; customer_id: string; amount_cents: number; status: string };
export const listInvoices = () => request<Invoice[]>("/billing/invoices");
export type PaymentLink = { session_id: string; customer_email: string; amount_cents: number; url: string; status: string };
export const listPaymentLinks = (email: string) => request<PaymentLink[]>(`/billing/payment-links?email=${encodeURIComponent(email)}`);
export const createPaymentLink = (customerEmail: string, amountCents: number) =>
  request<{ session_id: string; url: string; status: string }>("/billing/payment-links", {
    method: "POST", body: JSON.stringify({ customer_email: customerEmail, amount_cents: amountCents, recurring: false }),
  });

// 2FA enrollment
export const twofaSetup = () => request<{ secret: string; provisioning_uri: string }>("/auth/2fa/setup", { method: "POST" });
export const regenerateBackupCodes = (password: string, currentCode: string) =>
  request<{ backup_codes: string[]; reauthentication_required: boolean }>("/auth/2fa/backup-codes/regenerate", {
    method: "POST", body: JSON.stringify({ password, current_code: currentCode }),
  });
export const twofaVerify = (secret: string, code: string, password: string, currentCode?: string) =>
  request<{ enabled: boolean; reauthentication_required: boolean; backup_codes: string[] }>("/auth/2fa/verify-setup", {
    method: "POST", body: JSON.stringify({ secret, code, password, current_code: currentCode || null }),
  });

/* ---------- Audit trail ----------
 * Cursor-paginated, not offset-paginated, and with no total. A COUNT over a filtered multi-million-row
 * table is what makes an audit page unusable, and the number is not worth a full scan: what an operator
 * needs is the next page and whether one exists.
 */
export type AuditEvent = {
  event_id: string; action: string; category: string; outcome: string;
  message: string | null; occurred_at: string;
  actor_type: string; actor_id: string | null; actor_label: string | null;
  on_behalf_of: string | null;
  target_type: string; target_id: string | null; target_label: string | null;
  tenant_id: string | null; request_id: string | null;
  source_ip: string | null; user_agent: string | null; route: string | null;
  service: string; environment: string;
  changes: Record<string, { from?: unknown; to?: unknown }>;
  metadata: Record<string, unknown>;
  reason: string | null;
  /** Opaque. Carries the whole sort key, so paging cannot skip a row whose timestamp and id disagree. */
  _cursor: string;
};

export type AuditPage = {
  items: AuditEvent[]; next_cursor: string | null; has_more: boolean;
  window_days: number;
  /** How many action types this reader is not permitted to see. Stated so an operator who cannot read
   *  spend events knows they exist rather than concluding nothing happened. */
  hidden_actions: number;
};

export type AuditFilters = {
  days?: number; action?: string; category?: string; outcome?: string;
  tenant_id?: string; actor_id?: string; target_id?: string; request_id?: string;
  search?: string; cursor?: string | null; limit?: number;
};

export const auditEvents = (filters: AuditFilters) => {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  return request<AuditPage>(`/admin/audit?${query.toString()}`);
};

export type AuditCatalogue = {
  categories: string[];
  actions: { action: string; category: string; target_type: string }[];
};

/** The action taxonomy, from the same registry the writer uses. A hardcoded filter list would drift
 *  the first time an action was added. */
export const auditCatalogue = () => request<AuditCatalogue>("/admin/audit/actions");

export type AuditRetention = {
  event_retention_days: number; network_retention_days: number;
  erasure: string; archive: string;
};

export const auditRetention = () => request<AuditRetention>("/admin/audit/retention");
