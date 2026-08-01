import { createHash, createHmac, randomBytes } from "node:crypto";
import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type BrowserContext,
  type Page,
  type Response,
} from "@playwright/test";
import {
  COOKIES_RELEASE_ID,
  PRIVACY_RELEASE_ID,
  TERMS_RELEASE_ID,
} from "../../apps/creator/lib/consent/consent-record";

const LOCAL_RUN = process.env.QIKO_LOCAL === "1";
const PORT = process.env.QIKO_DEV_HTTP_PORT ?? "8080";
const TOTP_WINDOW_MS = 30_000;
const TOTP_MIN_REMAINING_MS = 10_000;

if (LOCAL_RUN && (!/^\d+$/.test(PORT) || Number(PORT) < 1 || Number(PORT) > 65535)) {
  throw new Error("QIKO_DEV_HTTP_PORT must be an integer between 1 and 65535.");
}

const CREATOR_ORIGIN = `http://qiko.localhost:${PORT}`;
const ADMIN_ORIGIN = `http://admin.qiko.localhost:${PORT}`;
const ALLOWED_ORIGINS = new Set([CREATOR_ORIGIN, ADMIN_ORIGIN]);
const EXPECTED_CREATOR_ERROR_RESPONSES = new Set([
  "GET /api/v1/consent 401",
  "POST /api/v1/consent 401",
  "POST /api/v1/auth/refresh 403",
  "GET /api/v1/consent 404",
]);
const ADMIN_EMAIL = process.env.LOCAL_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.LOCAL_ADMIN_PASSWORD;

function decodeBase32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bytes: number[] = [];
  let bits = 0;
  let value = 0;

  for (const character of secret.replace(/=+$/u, "").replace(/\s/gu, "").toUpperCase()) {
    const index = alphabet.indexOf(character);
    if (index < 0) throw new Error("The local 2FA API returned an invalid TOTP secret.");
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
      value &= (1 << bits) - 1;
    }
  }

  if (bytes.length === 0) throw new Error("The local 2FA API returned an invalid TOTP secret.");
  return Buffer.from(bytes);
}

function totpCounter(time = Date.now()): number {
  return Math.floor(time / TOTP_WINDOW_MS);
}

function totpWindowRemaining(time = Date.now()): number {
  return TOTP_WINDOW_MS - (time % TOTP_WINDOW_MS);
}

type Clock = () => number;
type Sleeper = (milliseconds: number) => Promise<void>;

const systemClock: Clock = () => Date.now();
const systemSleep: Sleeper = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitForSafeTotpWindow(
  minimumRemaining = TOTP_MIN_REMAINING_MS,
  clock: Clock = systemClock,
  sleep: Sleeper = systemSleep,
): Promise<number> {
  const remaining = totpWindowRemaining(clock());
  if (remaining < minimumRemaining) await sleep(remaining + 250);
  return totpCounter(clock());
}

async function waitForLaterTotpCounter(
  previousCounter: number,
  clock: Clock = systemClock,
  sleep: Sleeper = systemSleep,
): Promise<number> {
  while (totpCounter(clock()) <= previousCounter) {
    await sleep(totpWindowRemaining(clock()) + 250);
  }
  return waitForSafeTotpWindow(TOTP_MIN_REMAINING_MS, clock, sleep);
}

function totp(secret: string, time = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(totpCounter(time)));
  const digest = createHmac("sha1", decodeBase32(secret)).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const binary = ((digest[offset] & 0x7f) << 24)
    | ((digest[offset + 1] & 0xff) << 16)
    | ((digest[offset + 2] & 0xff) << 8)
    | (digest[offset + 3] & 0xff);
  return String(binary % 1_000_000).padStart(6, "0");
}

function sanitizedTarget(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    return `${url.hostname}${url.pathname}`;
  } catch {
    return "invalid-url";
  }
}

function endpoint(rawUrl: string): string {
  const url = new URL(rawUrl);
  return `${url.origin}${url.pathname}`;
}

function isAllowedWebSocket(rawUrl: string): boolean {
  const url = new URL(rawUrl);
  const browserProtocol = url.protocol === "ws:" ? "http:" : url.protocol === "wss:" ? "https:" : "";
  return browserProtocol !== "" && ALLOWED_ORIGINS.has(`${browserProtocol}//${url.host}`);
}

function requireStatus(response: APIResponse | Response, expected: number): void {
  if (response.status() !== expected) {
    throw new Error(`${endpoint(response.url())} returned status ${response.status()}, expected ${expected}.`);
  }
}

function headerTokens(value: string | undefined): Set<string> {
  return new Set((value ?? "").split(",").map((token) => token.trim().toLowerCase()).filter(Boolean));
}

function isApiResponse(response: Response, origin: string, path: string, method: string): boolean {
  const url = new URL(response.url());
  return url.origin === origin && url.pathname === path && response.request().method() === method;
}

function localGet(
  request: APIRequestContext,
  url: string,
  options: Parameters<APIRequestContext["get"]>[1] = {},
): Promise<APIResponse> {
  return request.get(url, { ...options, maxRedirects: 0 });
}

function localFetch(
  request: APIRequestContext,
  url: string,
  options: Parameters<APIRequestContext["fetch"]>[1] = {},
): Promise<APIResponse> {
  return request.fetch(url, { ...options, maxRedirects: 0 });
}

function localPost(
  request: APIRequestContext,
  url: string,
  options: Parameters<APIRequestContext["post"]>[1] = {},
): Promise<APIResponse> {
  return request.post(url, { ...options, maxRedirects: 0 });
}

function disposablePassword(): string {
  return `Qk!${randomBytes(24).toString("base64url")}9a`;
}

async function requestCookie(
  request: APIRequestContext,
  name: string,
): Promise<{ value: string; digest: string }> {
  const cookie = (await request.storageState()).cookies.find((candidate) => candidate.name === name);
  if (!cookie) throw new Error("The expected local API session cookie was not set.");
  return {
    value: cookie.value,
    digest: createHash("sha256").update(cookie.value).digest("hex"),
  };
}

async function requireRequestCookieRemoved(request: APIRequestContext, name: string): Promise<void> {
  const present = (await request.storageState()).cookies.some((cookie) => cookie.name === name);
  if (present) throw new Error("Local API logout did not remove an authentication cookie.");
}

function requireSecretField(
  body: Record<string, unknown>,
  field: string,
  pattern?: RegExp,
): string {
  const value = body[field];
  if (typeof value !== "string" || value.length === 0 || (pattern && !pattern.test(value))) {
    throw new Error(`The local API response did not include a valid ${field} field.`);
  }
  return value;
}

async function dismissOptionalCreatorConsent(page: Page): Promise<void> {
  const rejectNonEssential = page.getByRole("button", { name: "Reject non-essential", exact: true });
  const visible = await rejectNonEssential.waitFor({ state: "visible", timeout: 2_000 })
    .then(() => true, () => false);
  if (visible) {
    await rejectNonEssential.click();
    await expect(rejectNonEssential).toBeHidden();
  }
}

async function submitAdminLogin(page: Page, secondFactor?: string): Promise<Response> {
  await page.goto(`${ADMIN_ORIGIN}/login`);
  await page.locator("#email").fill(ADMIN_EMAIL!);
  await page.locator("#password").fill(ADMIN_PASSWORD!);
  if (secondFactor) await page.locator("#totp").fill(secondFactor);
  const responsePromise = page.waitForResponse((response) =>
    isApiResponse(response, ADMIN_ORIGIN, "/api/v1/auth/login", "POST"));
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  return responsePromise;
}

async function accessCookie(
  context: BrowserContext,
  origin = ADMIN_ORIGIN,
): Promise<{ value: string; digest: string }> {
  const cookie = (await context.cookies([origin])).find((candidate) => candidate.name === "qiko_access");
  if (!cookie) throw new Error("The expected local access cookie was not set.");
  return {
    value: cookie.value,
    digest: createHash("sha256").update(cookie.value).digest("hex"),
  };
}

async function requireRejectedCookie(
  request: APIRequestContext,
  origin: string,
  path: string,
  cookieValue: string,
): Promise<void> {
  if (!ALLOWED_ORIGINS.has(origin) || !path.startsWith("/api/")) {
    throw new Error("Cookie replay must target an allowed local API endpoint.");
  }
  const response = await localGet(request, `${origin}${path}`, {
    headers: { Cookie: `qiko_access=${cookieValue}` },
  });
  requireStatus(response, 401);
}

async function requireAccessCookieRemoved(context: BrowserContext): Promise<void> {
  const present = (await context.cookies([ADMIN_ORIGIN])).some((cookie) => cookie.name === "qiko_access");
  if (present) throw new Error("Local logout did not remove the browser access cookie.");
}

function requireRotatedCookie(previousDigest: string, nextDigest: string): void {
  if (previousDigest === nextDigest) throw new Error("The local access cookie did not rotate after login.");
}

let runtimeFailures = new Set<string>();
let expectedBrowserResponses = new Set<string>();

function browserResponseSignature(origin: string, method: string, path: string, status: number): string {
  return `${origin} ${method} ${path} ${status}`;
}

test.describe("Local development contract", () => {
  test.skip(!LOCAL_RUN, "set QIKO_LOCAL=1 to run local-only checks");
  test.describe.configure({ mode: "serial", timeout: 180_000 });

  test.beforeEach(async ({ context, page }) => {
    runtimeFailures = new Set<string>();
    expectedBrowserResponses = new Set<string>();
    const recordExternal = (kind: string, rawUrl: string) => {
      runtimeFailures.add(`${kind}: ${sanitizedTarget(rawUrl)}`);
    };

    await context.route("**/*", async (route) => {
      const origin = new URL(route.request().url()).origin;
      if (ALLOWED_ORIGINS.has(origin)) await route.continue();
      else {
        recordExternal("external request", route.request().url());
        await route.abort("blockedbyclient");
      }
    });
    await page.routeWebSocket("**/*", (webSocket) => {
      if (isAllowedWebSocket(webSocket.url())) webSocket.connectToServer();
      else {
        recordExternal("external WebSocket", webSocket.url());
        webSocket.close();
      }
    });
    page.on("websocket", (webSocket) => {
      if (!isAllowedWebSocket(webSocket.url())) recordExternal("external WebSocket", webSocket.url());
    });
    context.on("serviceworker", (worker) => {
      if (!ALLOWED_ORIGINS.has(new URL(worker.url()).origin)) {
        recordExternal("external service worker", worker.url());
      }
    });
    page.on("response", (response) => {
      if (response.status() < 400) return;
      const url = new URL(response.url());
      const method = response.request().method();
      const globalSignature = `${method} ${url.pathname} ${response.status()}`;
      if (url.origin === CREATOR_ORIGIN && EXPECTED_CREATOR_ERROR_RESPONSES.has(globalSignature)) return;
      const expectedSignature = browserResponseSignature(url.origin, method, url.pathname, response.status());
      if (expectedBrowserResponses.delete(expectedSignature)) return;
      runtimeFailures.add(`browser response: ${response.status()} ${method} ${url.pathname}`);
    });
    page.on("console", (message) => {
      if (message.type() !== "error" || message.text().trim().startsWith("Failed to load resource:")) return;
      runtimeFailures.add(`console error: ${sanitizedTarget(message.location().url)}`);
    });
    page.on("pageerror", () => runtimeFailures.add("page error"));
  });

  test.afterEach(() => {
    expect.soft([...runtimeFailures], "local pages must not make external requests or emit runtime errors").toEqual([]);
    expect([...expectedBrowserResponses], "expected browser responses must be observed exactly once").toEqual([]);
  });

  test("serves public Creator and Admin routes on their canonical origins", async ({ page }) => {
    const creatorHome = await page.goto(`${CREATOR_ORIGIN}/`);
    if (!creatorHome) throw new Error(`${CREATOR_ORIGIN}/ did not return a document response.`);
    requireStatus(creatorHome, 200);
    await expect(page).toHaveURL(`${CREATOR_ORIGIN}/`);
    await expect(page).toHaveTitle(/Qiko/);

    const creatorLogin = await page.goto(`${CREATOR_ORIGIN}/login`);
    if (!creatorLogin) throw new Error(`${CREATOR_ORIGIN}/login did not return a document response.`);
    requireStatus(creatorLogin, 200);
    await expect(page.getByText("Welcome back")).toBeVisible();

    const adminLogin = await page.goto(`${ADMIN_ORIGIN}/login`);
    if (!adminLogin) throw new Error(`${ADMIN_ORIGIN}/login did not return a document response.`);
    requireStatus(adminLogin, 200);
    await expect(page).toHaveURL(`${ADMIN_ORIGIN}/login`);
    await expect(page.getByText("Admin Sign In")).toBeVisible();

    const adminForgotPassword = await page.goto(`${ADMIN_ORIGIN}/forgot-password`);
    if (!adminForgotPassword) throw new Error(`${ADMIN_ORIGIN}/forgot-password did not return a document response.`);
    requireStatus(adminForgotPassword, 200);
    await expect(page.getByText("Forgot Password")).toBeVisible();
  });

  test("serves health, docs, and the runtime OpenAPI document", async ({ request }) => {
    for (const path of ["/health", "/api/v1/health"]) {
      const response = await localGet(request, `${CREATOR_ORIGIN}${path}`);
      requireStatus(response, 200);
      const body = await response.json() as { status?: string; service?: string; environment?: string };
      expect(body.status).toBe("ok");
      expect(body.service).toBe("qiko-core");
      expect(body.environment).toBe("dev");
    }

    const docs = await localGet(request, `${CREATOR_ORIGIN}/docs`);
    requireStatus(docs, 200);
    expect(docs.headers()["content-type"]).toContain("text/html");

    const openapi = await localGet(request, `${CREATOR_ORIGIN}/openapi.json`);
    requireStatus(openapi, 200);
    const schema = await openapi.json() as { info?: { title?: string }; paths?: Record<string, unknown> };
    expect(schema.info?.title).toBe("Qiko Core");
    expect(schema.paths).toHaveProperty("/health");
    expect(schema.paths).toHaveProperty("/api/v1/auth/login");
  });

  test("enforces credentialed CORS for the exact local browser origins", async ({ request }) => {
    const requestedHeaders = new Set(["content-type", "x-csrf-token"]);
    for (const origin of [CREATOR_ORIGIN, ADMIN_ORIGIN]) {
      const response = await localFetch(request, `${CREATOR_ORIGIN}/api/v1/health`, {
        method: "OPTIONS",
        headers: {
          Origin: origin,
          "Access-Control-Request-Method": "GET",
          "Access-Control-Request-Headers": [...requestedHeaders].join(", "),
        },
      });
      requireStatus(response, 200);
      const headers = response.headers();
      expect(headers["access-control-allow-origin"]).toBe(origin);
      expect(headers["access-control-allow-credentials"]?.toLowerCase()).toBe("true");
      const allowedHeaders = headerTokens(headers["access-control-allow-headers"]);
      const allowedMethods = headerTokens(headers["access-control-allow-methods"]);
      const vary = headerTokens(headers.vary);
      for (const header of requestedHeaders) expect(allowedHeaders.has(header)).toBe(true);
      expect(allowedMethods.has("get")).toBe(true);
      expect(vary.has("origin")).toBe(true);
    }

    const disallowedOrigin = `http://untrusted.qiko.localhost:${PORT}`;
    const rejected = await localFetch(request, `${CREATOR_ORIGIN}/api/v1/health`, {
      method: "OPTIONS",
      headers: {
        Origin: disallowedOrigin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
      },
    });
    requireStatus(rejected, 400);
    expect(rejected.headers()["access-control-allow-origin"]).toBeUndefined();
  });

  test("redirects Admin forgot-password completion to the Creator origin", async ({ page }) => {
    const email = `local-routing-${Date.now()}-${randomBytes(6).toString("hex")}@example.test`;
    await page.goto(`${ADMIN_ORIGIN}/forgot-password`);
    await page.locator("#email").fill(email);
    const responsePromise = page.waitForResponse((response) =>
      isApiResponse(response, ADMIN_ORIGIN, "/api/v1/auth/forgot-password", "POST"));
    await page.getByRole("button", { name: "Send one-time code" }).click();
    const response = await responsePromise;
    requireStatus(response, 200);
    await expect(page).toHaveURL(`${CREATOR_ORIGIN}/reset-password?email=${encodeURIComponent(email)}`);
  });

  test("denies an unauthenticated Admin API request", async ({ request }) => {
    const response = await localGet(request, `${ADMIN_ORIGIN}/api/v1/admin/overview`);
    requireStatus(response, 401);
  });

  test("repeatable local identity API lifecycle", async ({ request }) => {
    const apiBase = `${CREATOR_ORIGIN}/api/v1`;
    const email = `local-api-${Date.now()}-${randomBytes(8).toString("hex")}@example.test`;
    const password = disposablePassword();
    let newPassword = disposablePassword();
    while (newPassword === password) newPassword = disposablePassword();
    const policyAcceptance = {
      accept_policies: true,
      terms_release_id: TERMS_RELEASE_ID,
      privacy_release_id: PRIVACY_RELEASE_ID,
      cookies_release_id: COOKIES_RELEASE_ID,
    };

    const signup = await localPost(request, `${apiBase}/auth/signup`, {
      data: { email, password, ...policyAcceptance },
    });
    requireStatus(signup, 202);
    const signupBody = await signup.json() as Record<string, unknown>;
    const verificationCode = requireSecretField(signupBody, "verification_code", /^\d{6}$/u);

    const verification = await localPost(request, `${apiBase}/auth/verify-email`, {
      data: { email, code: verificationCode, password, ...policyAcceptance },
    });
    requireStatus(verification, 200);

    const login = await localPost(request, `${apiBase}/auth/login`, {
      data: { email, password },
    });
    requireStatus(login, 200);
    const initialAccess = await requestCookie(request, "qiko_access");
    await requestCookie(request, "qiko_refresh");
    const initialCsrf = await requestCookie(request, "qiko_csrf");

    const refresh = await localPost(request, `${apiBase}/auth/refresh`, {
      headers: { "x-csrf-token": initialCsrf.value },
    });
    requireStatus(refresh, 200);
    const refreshedAccess = await requestCookie(request, "qiko_access");
    requireRotatedCookie(initialAccess.digest, refreshedAccess.digest);
    const refreshedCsrf = await requestCookie(request, "qiko_csrf");

    const logout = await localPost(request, `${apiBase}/auth/logout`, {
      headers: { "x-csrf-token": refreshedCsrf.value },
    });
    requireStatus(logout, 200);
    await requireRequestCookieRemoved(request, "qiko_access");
    await requireRequestCookieRemoved(request, "qiko_refresh");
    await requireRequestCookieRemoved(request, "qiko_csrf");
    await requireRejectedCookie(request, CREATOR_ORIGIN, "/api/v1/auth/me", refreshedAccess.value);

    const forgotPassword = await localPost(request, `${apiBase}/auth/forgot-password`, {
      data: { email },
    });
    requireStatus(forgotPassword, 200);
    const forgotBody = await forgotPassword.json() as Record<string, unknown>;
    const resetOtp = requireSecretField(forgotBody, "otp", /^\d{6}$/u);

    const resetPassword = await localPost(request, `${apiBase}/auth/reset-password`, {
      data: { email, otp: resetOtp, new_password: newPassword },
    });
    requireStatus(resetPassword, 200);

    const oldPasswordLogin = await localPost(request, `${apiBase}/auth/login`, {
      data: { email, password },
    });
    requireStatus(oldPasswordLogin, 401);

    const newPasswordLogin = await localPost(request, `${apiBase}/auth/login`, {
      data: { email, password: newPassword },
    });
    requireStatus(newPasswordLogin, 200);
    const enrollmentCsrf = await requestCookie(request, "qiko_csrf");

    const setup = await localPost(request, `${apiBase}/auth/2fa/setup`, {
      headers: { "x-csrf-token": enrollmentCsrf.value },
    });
    requireStatus(setup, 200);
    const setupBody = await setup.json() as Record<string, unknown>;
    const secret = requireSecretField(setupBody, "secret");

    await waitForSafeTotpWindow();
    const verifySetup = await localPost(request, `${apiBase}/auth/2fa/verify-setup`, {
      headers: { "x-csrf-token": enrollmentCsrf.value },
      data: { secret, code: totp(secret), password: newPassword },
    });
    requireStatus(verifySetup, 200);
    const verifySetupBody = await verifySetup.json() as { enabled?: unknown };
    if (verifySetupBody.enabled !== true) throw new Error("The local 2FA enrollment did not report enabled state.");

    const passwordOnlyAfterEnrollment = await localPost(request, `${apiBase}/auth/login`, {
      data: { email, password: newPassword },
    });
    requireStatus(passwordOnlyAfterEnrollment, 401);

    const mfaLogin = await localPost(request, `${apiBase}/auth/login`, {
      data: { email, password: newPassword, totp: totp(secret) },
    });
    requireStatus(mfaLogin, 200);
    await requestCookie(request, "qiko_access");

    const nonPlatformAdmin = await localGet(request, `${apiBase}/admin/overview`);
    requireStatus(nonPlatformAdmin, 403);
  });

  test("enrolls local Admin MFA and verifies rotated TOTP and backup-code sessions", async ({ page, request }) => {
    test.skip(!ADMIN_EMAIL || !ADMIN_PASSWORD,
      "set LOCAL_ADMIN_EMAIL and LOCAL_ADMIN_PASSWORD to run the local credential flow");

    await page.goto(`${CREATOR_ORIGIN}/login`);
    await dismissOptionalCreatorConsent(page);
    await page.locator("#email").fill(ADMIN_EMAIL!);
    await page.locator("#password").fill(ADMIN_PASSWORD!);
    const creatorLoginPromise = page.waitForResponse((response) =>
      isApiResponse(response, CREATOR_ORIGIN, "/api/v1/auth/login", "POST"));
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    const creatorLogin = await creatorLoginPromise;
    requireStatus(creatorLogin, 200);
    const creatorCookie = await accessCookie(page.context(), CREATOR_ORIGIN);
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByText(/worker slots used/i)).toBeVisible();
    const creatorLogout = page.getByRole("button", { name: "Logout", exact: true });
    await expect(creatorLogout).toBeVisible();
    await creatorLogout.focus();
    await expect(creatorLogout).toBeFocused();
    await creatorLogout.press("Enter");
    await expect(page).toHaveURL(/\/login$/);
    await requireAccessCookieRemoved(page.context());
    await requireRejectedCookie(request, CREATOR_ORIGIN, "/api/v1/auth/me", creatorCookie.value);

    expectedBrowserResponses.add(browserResponseSignature(
      ADMIN_ORIGIN, "GET", "/api/v1/admin/overview", 403,
    ));
    const initialLogin = await submitAdminLogin(page);
    requireStatus(initialLogin, 200);
    const initialBody = await initialLogin.json() as { user?: { twofa_enabled?: boolean } };
    if (initialBody.user?.twofa_enabled !== false) {
      throw new Error("The disposable local Admin identity must start without MFA enabled.");
    }
    const passwordCookie = await accessCookie(page.context());
    await expect(page).toHaveURL(/\/overview$/);

    await page.goto(`${ADMIN_ORIGIN}/security`);
    await expect(page.getByRole("button", { name: "Enable 2FA" })).toBeVisible();
    const setupPromise = page.waitForResponse((response) =>
      isApiResponse(response, ADMIN_ORIGIN, "/api/v1/auth/2fa/setup", "POST"));
    await page.getByRole("button", { name: "Enable 2FA" }).click();
    const setupResponse = await setupPromise;
    requireStatus(setupResponse, 200);
    const setupBody = await setupResponse.json() as { secret?: unknown };
    if (typeof setupBody.secret !== "string" || setupBody.secret.length === 0) {
      throw new Error("The local 2FA setup API returned an invalid secret.");
    }
    const secret = setupBody.secret;

    const setupCounter = await waitForSafeTotpWindow();
    await page.locator("#password").fill(ADMIN_PASSWORD!);
    await page.locator("#code").fill(totp(secret));
    const verifyPromise = page.waitForResponse((response) =>
      isApiResponse(response, ADMIN_ORIGIN, "/api/v1/auth/2fa/verify-setup", "POST"));
    await page.getByRole("button", { name: "Verify & complete setup" }).click();
    const verifyResponse = await verifyPromise;
    requireStatus(verifyResponse, 200);
    const verifyBody = await verifyResponse.json() as { enabled?: unknown; backup_codes?: unknown };
    if (verifyBody.enabled !== true || !Array.isArray(verifyBody.backup_codes)
      || typeof verifyBody.backup_codes[0] !== "string") {
      throw new Error("The local 2FA verification API did not return the expected result.");
    }
    const backupCode = verifyBody.backup_codes[0];

    const oldPasswordSession = await localGet(request, `${ADMIN_ORIGIN}/api/v1/admin/overview`, {
      headers: { Cookie: `qiko_access=${passwordCookie.value}` },
    });
    requireStatus(oldPasswordSession, 401);

    await expect(page.getByText("Save these one-time backup codes now. They will not be shown again.")).toBeVisible();
    await page.getByRole("button", { name: "I've saved these codes, sign in" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await waitForLaterTotpCounter(setupCounter);
    const totpLogin = await submitAdminLogin(page, totp(secret));
    requireStatus(totpLogin, 200);
    const totpCookie = await accessCookie(page.context());
    requireRotatedCookie(passwordCookie.digest, totpCookie.digest);
    await expect(page).toHaveURL(/\/overview$/);
    const overviewPromise = page.waitForResponse((response) =>
      isApiResponse(response, ADMIN_ORIGIN, "/api/v1/admin/overview", "GET"));
    await page.goto(`${ADMIN_ORIGIN}/overview`);
    requireStatus(await overviewPromise, 200);

    await page.getByRole("button", { name: /sign out/i }).first().click();
    await expect(page).toHaveURL(/\/login$/);
    await requireAccessCookieRemoved(page.context());
    await requireRejectedCookie(request, ADMIN_ORIGIN, "/api/v1/admin/overview", totpCookie.value);

    const backupLogin = await submitAdminLogin(page, backupCode);
    requireStatus(backupLogin, 200);
    const backupCookie = await accessCookie(page.context());
    requireRotatedCookie(totpCookie.digest, backupCookie.digest);
    requireRotatedCookie(passwordCookie.digest, backupCookie.digest);
    await expect(page).toHaveURL(/\/overview$/);
    await page.getByRole("button", { name: /sign out/i }).first().click();
    await expect(page).toHaveURL(/\/login$/);
    await requireAccessCookieRemoved(page.context());
    await requireRejectedCookie(request, ADMIN_ORIGIN, "/api/v1/admin/overview", backupCookie.value);

    expectedBrowserResponses.add(browserResponseSignature(
      ADMIN_ORIGIN, "POST", "/api/v1/auth/login", 401,
    ));
    const replay = await submitAdminLogin(page, backupCode);
    requireStatus(replay, 401);
    await expect(page).toHaveURL(/\/login$/);
    await requireAccessCookieRemoved(page.context());
  });
});
