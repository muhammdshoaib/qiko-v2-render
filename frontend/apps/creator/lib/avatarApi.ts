"use client";
import type { OnboardingWorkerConfig, OnboardingWorkerSignup } from "./onboarding-worker";

// Compatibility shim: exposes the qiko-frontend avatarApi surface, backed by the V2 /api/v1 FastAPI.
import { clientApiBase } from "@/lib/api-origin";

const BASE = clientApiBase();

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isColdStartStatus(status: number) {
  return status === 502 || status === 503 || status === 504;
}

async function req<T = unknown>(path: string, opts: RequestInit = {}, retries = 0): Promise<T> {
  let lastError = new Error("Request failed");
  for (let attempt = 0; attempt <= retries; attempt++) {
    const res = await fetch(`${BASE}${path}`, {
      ...opts,
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      credentials: "include",
    });
    if (res.ok) {
      return res.status === 204 ? (undefined as T) : res.json();
    }
    let detail = `Request failed (${res.status})`;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    lastError = new Error(detail);
    if (!isColdStartStatus(res.status) || attempt === retries) break;
    await sleep(4000);
  }
  throw lastError;
}

export interface SubscriptionPlan {
  key: string;
  id: number;
  name: string;
  display_name: string;
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

export async function saveAvatarProfile(agentId: string, config: OnboardingWorkerConfig) {
  return req(`/agents/${agentId}/config`, {
    method: "PUT",
    body: JSON.stringify({ patch: config }),
  });
}

export async function addAvatarKnowledge(agentId: string, text: string) {
  const normalizedAgentId = agentId.trim();
  if (!normalizedAgentId) throw new Error("Agent id is required to save worker knowledge");

  return req("/knowledge/ingest", {
    method: "POST",
    body: JSON.stringify({ doc_id: normalizedAgentId, text, agent_id: normalizedAgentId }),
  });
}

export async function loginAvatar(body: { email: string; password: string; totp?: string }) {
  // V2 sets an httpOnly cookie; there is no client token. Return a truthy token so the
  // ported UI's success branch runs, plus the user object.
  // `totp` is required by POST /auth/login as soon as the account has 2FA enabled -- omitting it
  // returned 401 "Invalid or missing 2FA code" and locked those users out of the creator app.
  const r = await req<{ user: Record<string, unknown> }>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  }, 4);
  return { data: { token: "cookie", user: r.user } };
}

export async function signupAvatar(body: {
  user_name: string;
  email: string;
  password?: string;
  invite_token?: string;
  onboarding_worker?: OnboardingWorkerSignup;
  terms_release_id: string;
  privacy_release_id: string;
  cookies_release_id: string;
}) {
  return req("/auth/signup", {
    method: "POST",
    // `name` is forwarded: it used to be accepted here as user_name and silently dropped, so every
    // account was created with no display name.
    // Password is selected during email verification, not at signup.
    body: JSON.stringify({
      email: body.email,
      name: body.user_name,
      invite_token: body.invite_token,
      onboarding_worker: body.onboarding_worker,
      accept_policies: true,
      terms_release_id: body.terms_release_id,
      privacy_release_id: body.privacy_release_id,
      cookies_release_id: body.cookies_release_id,
      ...(body.password ? { password: body.password } : {}),
    }),
  });
}

export async function forgotPasswordAvatar(email: string) {
  return req("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
}

export async function resetPasswordAvatar(body: { email: string; otp: string; password: string }) {
  return req<{ reset: boolean }>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ email: body.email, otp: body.otp, new_password: body.password }),
  });
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
