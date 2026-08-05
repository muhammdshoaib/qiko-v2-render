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

export type Customer = { user_id: string; email: string; plan: string; earnings_cents: number };
export const listCustomers = (search = "", page = 1) => {
  const params = new URLSearchParams({ page: String(page) });
  if (search) params.set("search", search);
  return request<{ total: number; page: number; items: Customer[] }>(`/admin/customers?${params}`);
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
export type Capability = "view_customers" | "manage_customers" | "manage_workers" | "manage_billing" | "manage_admins";

export const ALL_CAPABILITIES: Capability[] = ["view_customers", "manage_customers", "manage_workers", "manage_billing", "manage_admins"];

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
  platform_role: AdminRole | null; platform_capabilities: Capability[];
};
export type WorkerRow = AdminWorker & { tenant_id: string };

type Paged<T> = { total: number; page: number; items: T[] };

const paged = (page: number, extra: Record<string, string | undefined> = {}) => {
  const params = new URLSearchParams({ page: String(page) });
  for (const [key, value] of Object.entries(extra)) if (value) params.set(key, value);
  return params;
};

export const listTenants = (search = "", page = 1) =>
  request<Paged<TenantRow>>(`/admin/tenants?${paged(page, { search })}`);
export const listUsers = (search = "", page = 1, tenantId?: string) =>
  request<Paged<UserRow>>(`/admin/users?${paged(page, { search, tenant_id: tenantId })}`);
export const listWorkers = (search = "", page = 1, enabled?: boolean) =>
  request<Paged<WorkerRow>>(
    `/admin/workers?${paged(page, { search, enabled: enabled === undefined ? undefined : String(enabled) })}`);

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
export const listPlatformAdminAudit = () =>
  request<{ entries: AdminGrantAudit[] }>("/admin/org/audit");
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
