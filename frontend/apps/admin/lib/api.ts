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

export const login = (email: string, password: string) =>
  request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => request("/auth/logout", { method: "POST" });
export const forgotPassword = (email: string) =>
  request("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });

export type Customer = { user_id: string; email: string; plan: string; earnings_cents: number };
export const listCustomers = (search = "") =>
  request<{ total: number; page: number; items: Customer[] }>(
    `/admin/customers${search ? `?search=${encodeURIComponent(search)}` : ""}`,
  );

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

// 2FA enrollment
export const twofaSetup = () => request<{ secret: string; provisioning_uri: string }>("/auth/2fa/setup", { method: "POST" });
export const twofaVerify = (secret: string, code: string) =>
  request<{ enabled: boolean }>("/auth/2fa/verify-setup", { method: "POST", body: JSON.stringify({ secret, code }) });
