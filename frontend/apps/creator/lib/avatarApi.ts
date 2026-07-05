"use client";
// Compatibility shim: exposes the qiko-frontend avatarApi surface, backed by the V2 /api/v1 FastAPI.
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

async function req<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    credentials: "include",
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export interface SubscriptionPlan {
  id: number;
  name: string;
  price_id: string;
  amount: number;
  display_price?: string | number;
  interval: string;
  description?: string;
  feature?: string;
  features?: string[];
}

export async function createAvatar(body: { agent_name: string }) {
  const a = await req<{ id: string; name: string; status: string }>("/agents", {
    method: "POST",
    body: JSON.stringify({ name: body.agent_name, plan: "free" }),
  });
  return { data: { agent_unique_id: a.id, ...a } };
}

export async function addAvatarKnowledge(payload: Record<string, unknown>) {
  const docId = String(payload.agent_unique_id || `onboard-${Date.now()}`);
  const text = [payload.full_name, payload.headline, payload.about_yourself, payload.short_bio,
                payload.expertise, payload.strength]
    .filter(Boolean).join("\n\n") || JSON.stringify(payload);
  return req("/knowledge/ingest", { method: "POST", body: JSON.stringify({ doc_id: docId, text }) });
}

export async function loginAvatar(body: { email: string; password: string }) {
  // V2 sets an httpOnly cookie; there is no client token. Return a truthy token so the
  // ported UI's success branch runs, plus the user object.
  const r = await req<{ user: Record<string, unknown> }>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return { data: { token: "cookie", user: r.user } };
}

export async function signupAvatar(body: { user_name: string; email: string; password: string }) {
  const tenant = body.email.split("@")[0].toLowerCase();
  await req("/auth/signup", { method: "POST", body: JSON.stringify({ tenant, email: body.email, password: body.password }) });
  // establish the session cookie so the subsequent authed create calls work
  return req("/auth/login", { method: "POST", body: JSON.stringify({ email: body.email, password: body.password }) });
}

export async function getSubscriptionPlans(): Promise<SubscriptionPlan[]> {
  return req<SubscriptionPlan[]>("/billing/plans");
}

export async function createSignalWorker(body: {
  agent_name: string; signal_brand?: string; signal_domain?: string;
  signal_competitors?: string[]; signal_query_sets?: Record<string, string[]>;
}) {
  return req("/signal/projects", {
    method: "POST",
    body: JSON.stringify({ brand: body.signal_brand || body.agent_name, domain: body.signal_domain || "example.com" }),
  });
}
