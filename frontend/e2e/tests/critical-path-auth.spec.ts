import { expect, test, type Page, type Route } from "@playwright/test";

// Critical-path auth coverage for BOTH apps and BOTH audiences:
//   - creator (qiko.ai)  -> normal tenant users
//   - admin (admin.*)    -> platform admins (MFA is mandatory there)
//
// Everything here is deterministic and side-effect free: server responses are intercepted with
// page.route, so no account is created, no password is submitted to a real backend, and no data is
// mutated. That is what makes it safe to run against preprod on every change.
//
// The two regressions these lock down:
//   1. The creator login page had NO 2FA field and never sent `totp`, while POST /auth/login
//      requires it as soon as an account has 2FA enabled. Any user who enrolled 2FA (which the
//      admin panel pushes them to do) was permanently locked out of qiko.ai.
//   2. The register form collected a display name that was silently dropped before the request, so
//      every account was created nameless.

// Same convention as the other admin specs (e2e/tests/admin.spec.ts).
const ADMIN_BASE_URL = process.env.ADMIN_BASE_URL ?? "https://admin.preprod.qiko.ai";

/** Pre-seed a consent decision so the cookie banner never mounts.
 *
 *  Clicking the banner away is inherently racy: it mounts asynchronously after a consent probe, so a
 *  `count()` check or even a bounded `waitFor` can miss it, and once mounted it OVERLAYS the Sign in
 *  button, making every subsequent click time out. Writing a valid decision before any page script
 *  runs removes the banner from the equation entirely, which is what makes these tests stable.
 *  Shape mirrors apps/creator/lib/consent/consent-record.ts (schemaVersion 1, policy 2026-07-24).
 */
async function seedConsent(page: Page) {
  await page.addInitScript(() => {
    const now = new Date();
    const expires = new Date(now.getTime());
    expires.setUTCFullYear(expires.getUTCFullYear() + 1);
    const timestamp = now.toISOString();
    const record = {
      schemaVersion: 1,
      decisionId: `e2e-${timestamp}`,
      revision: now.getTime(),
      policyVersion: "2026-07-24",
      necessary: true,
      preferences: false,
      analytics: false,
      marketing: false,
      source: "banner",
      decidedAt: timestamp,
      updatedAt: timestamp,
      expiresAt: expires.toISOString(),
      signals: { gpc: false, dnt: false },
    };
    try {
      window.localStorage.setItem("qiko.consent.v1", JSON.stringify(record));
    } catch {
      // Storage disabled in this context; the banner assertions below simply do not apply.
    }
  });
}

/** Kept for the rare case a banner still renders (e.g. storage blocked): never fails the test. */
async function dismissConsent(page: Page) {
  const reject = page.getByRole("button", { name: "Reject non-essential" }).first();
  if (await reject.isVisible().catch(() => false)) {
    await reject.click().catch(() => {});
    await reject.waitFor({ state: "hidden", timeout: 5000 }).catch(() => {});
  }
}

/** Fail the test on any uncaught page error: an auth screen must never crash. */
function trackPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

test.beforeEach(async ({ page }) => {
  await seedConsent(page);
  // /api/v1/consent sits on the STRICT rate limiter (10/min per IP+path). Across a suite this file
  // would exhaust that budget, the sync would start returning 429, the provider would fall back to
  // "undecided", and the banner would remount mid-suite and block clicks -- which is exactly the
  // cross-test flakiness observed (each test passes alone, later ones fail in a batch). Serving the
  // consent endpoints locally keeps the tests hermetic and stops the suite hammering a shared env.
  await page.route("**/api/v1/consent**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) }));
});

function jsonRoute(route: Route, status: number, body: unknown) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

test.describe("creator login (normal user)", () => {
  test("renders the form and shows a clear error for bad credentials", async ({ page }) => {
    const errors = trackPageErrors(page);
    await page.route("**/api/v1/auth/login", (route) =>
      jsonRoute(route, 401, { detail: "Invalid credentials" }));

    await page.goto("/login");
    await dismissConsent(page);
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    // No 2FA field until the server asks for one: the common case stays a two-field form.
    await expect(page.locator("#totp")).toHaveCount(0);

    await page.locator("#email").fill("nobody" + "@" + "example.invalid");
    await page.locator("#password").fill("wrong-password");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByText(/invalid credentials/i).first()).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
    expect(errors).toEqual([]);
  });

  test("reveals the 2FA field when the account requires it, and retries with the code", async ({ page }) => {
    const errors = trackPageErrors(page);
    const sentBodies: Array<Record<string, unknown>> = [];

    await page.route("**/api/v1/auth/login", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      sentBodies.push(body);
      if (!body.totp) {
        // Exactly what the real backend returns for a 2FA account with no code.
        return jsonRoute(route, 401, { detail: "Invalid or missing 2FA code" });
      }
      return jsonRoute(route, 200, { user: { id: "u1", email: body.email, role: "owner" } });
    });

    await page.goto("/login");
    await dismissConsent(page);
    await page.locator("#email").fill("twofa" + "@" + "example.invalid");
    await page.locator("#password").fill("correct-horse-battery-staple");
    await page.getByRole("button", { name: /sign in/i }).click();

    // The regression: this field did not exist, so the user could never get past this point.
    await expect(page.locator("#totp")).toBeVisible();
    await expect(page.getByText(/two-factor|authenticator/i).first()).toBeVisible();

    await page.locator("#totp").fill("123456");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect.poll(() => sentBodies.length).toBeGreaterThanOrEqual(2);
    expect(sentBodies[0].totp).toBeUndefined();
    expect(sentBodies[1].totp).toBe("123456"); // the code actually reaches the API
    expect(errors).toEqual([]);
  });

  test("a wrong 2FA code keeps the field visible and explains what to do", async ({ page }) => {
    await page.route("**/api/v1/auth/login", (route) =>
      jsonRoute(route, 401, { detail: "Invalid or missing 2FA code" }));

    await page.goto("/login");
    await dismissConsent(page);
    await page.locator("#email").fill("twofa" + "@" + "example.invalid");
    await page.locator("#password").fill("correct-horse-battery-staple");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.locator("#totp")).toBeVisible();

    await page.locator("#totp").fill("000000");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.locator("#totp")).toBeVisible();
    await expect(page.getByText(/backup code/i).first()).toBeVisible();
  });
});

test.describe("creator register (normal user)", () => {
  test("sends the display name to the API", async ({ page }) => {
    const errors = trackPageErrors(page);
    let signupBody: Record<string, unknown> | null = null;

    await page.route("**/api/v1/auth/signup", async (route) => {
      signupBody = JSON.parse(route.request().postData() ?? "{}");
      return jsonRoute(route, 202, { verification_required: true, email: signupBody.email, expires_in: 600 });
    });

    await page.goto("/signup");
    await dismissConsent(page);
    const name = page.locator("#name");
    await expect(name).toBeVisible();
    await name.fill("Ada Lovelace");
    await page.locator("#email").fill("ada" + "@" + "example.invalid");
    // Must satisfy lib/passwordRequirements.ts (8+ chars, upper, lower, digit, symbol) or the page
    // rejects the submit client-side and never calls the API.
    const strongPassword = "Playwright-Test-1!";
    await page.locator("#password").fill(strongPassword);
    const confirm = page.locator("#confirmPassword");
    if (await confirm.count()) await confirm.fill(strongPassword);
    for (const box of await page.locator('input[type="checkbox"]').all()) {
      await box.check().catch(() => {});
    }
    await page.getByRole("button", { name: /sign up|create account|continue/i }).first().click();

    // The regression: the form collected a name and dropped it, so accounts were created nameless.
    await expect.poll(() => signupBody).not.toBeNull();
    expect(signupBody!.name).toBe("Ada Lovelace");
    expect(signupBody!.email).toBe("ada" + "@" + "example.invalid");
    expect(errors).toEqual([]);
  });

  test("register is reachable anonymously and links back to login", async ({ page }) => {
    await page.goto("/signup");
    await dismissConsent(page);
    await expect(page).toHaveURL(/\/signup/);
    await expect(page.getByRole("link", { name: /sign in|log in/i }).first()).toBeVisible();
  });
});

test.describe("admin login (platform admin)", () => {
  test("exposes the MFA code field up front, because admin access requires 2FA", async ({ page }) => {
    const errors = trackPageErrors(page);
    await page.goto(`${ADMIN_BASE_URL}/login`);
    await dismissConsent(page);
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    // Admin endpoints require the `mfa` claim, so the field is always present here.
    await expect(page.locator("#totp")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("sends the code with the credentials", async ({ page }) => {
    let body: Record<string, unknown> | null = null;
    await page.route("**/api/v1/auth/login", async (route) => {
      body = JSON.parse(route.request().postData() ?? "{}");
      return jsonRoute(route, 401, { detail: "Invalid credentials" });
    });

    await page.goto(`${ADMIN_BASE_URL}/login`);
    await dismissConsent(page);
    await page.locator("#email").fill("admin" + "@" + "example.invalid");
    await page.locator("#password").fill("correct-horse-battery-staple");
    await page.locator("#totp").fill("654321");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect.poll(() => body).not.toBeNull();
    expect(body!.totp).toBe("654321");
  });

  test("a platform admin without 2FA is guided to enrol instead of dead-ending", async ({ page }) => {
    // Admin reads return 403 "platform admin MFA required" until TOTP is enrolled; the shell turns
    // that into a redirect to /security rather than an unexplained empty screen.
    await page.route("**/api/v1/admin/**", (route) =>
      jsonRoute(route, 403, { detail: "platform admin MFA required" }));
    await page.route("**/api/v1/auth/me", (route) =>
      jsonRoute(route, 200, { user: { id: "a1", email: "admin" + "@" + "example.invalid", role: "owner", name: null } }));

    await page.goto(`${ADMIN_BASE_URL}/overview`);
    await dismissConsent(page);
    await expect(page).toHaveURL(/\/security|\/login/);
  });
});

test.describe("auth guards", () => {
  test("an anonymous visitor is sent to login for a protected creator page", async ({ page }) => {
    await page.goto("/workers");
    await expect(page).toHaveURL(/\/login/);
  });

  test("public auth pages render for an anonymous visitor", async ({ page }) => {
    for (const path of ["/login", "/signup", "/forgot-password"]) {
      const errors = trackPageErrors(page);
      await page.goto(path);
      await dismissConsent(page);
      await expect(page).toHaveURL(new RegExp(path.replace("/", "\\/")));
      expect(errors).toEqual([]);
    }
  });
});

// A platform admin is ALSO a normal tenant user (every /admin endpoint additionally depends on
// authed_tenant) and MFA is mandatory for admin access. That combination is exactly what broke:
// enrol 2FA for the admin panel and the creator app becomes unreachable. These cover the admin
// account signing in to the CREATOR app (qiko.ai), not the admin host.
//
// middleware.ts gates the /dashboard document on the PRESENCE of the qiko_access cookie (it
// deliberately does not check validity), so the successful login stub sets that cookie exactly like
// the real backend does. Without it the document request bounces straight back to /login and the
// test would be measuring the middleware, not the login flow.
test.describe("admin account signing in to the creator app", () => {
  const ADMIN_EMAIL = "platform.admin" + "@" + "example.invalid";
  const ADMIN_PASSWORD = "Platform-Admin-1!";
  const ADMIN_USER = {
    id: "admin-1", email: ADMIN_EMAIL, name: "Platform Admin", tenant: "acme",
    role: "owner", twofa_enabled: true,
  };

  function loggedIn(route: Route) {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "set-cookie": "qiko_access=stub-session; Path=/; SameSite=Lax" },
      body: JSON.stringify({ user: ADMIN_USER }),
    });
  }

  /** The reads the creator app performs once a session exists. */
  async function stubCreatorSession(page: Page) {
    await page.route("**/api/v1/auth/me", (route) => jsonRoute(route, 200, { user: ADMIN_USER }));
    await page.route("**/api/v1/agents", (route) => jsonRoute(route, 200, []));
    await page.route("**/api/v1/agents/usage", (route) =>
      jsonRoute(route, 200, { used_count: 0, worker_limit: 1 }));
    await page.route("**/api/v1/notifications**", (route) => jsonRoute(route, 200, []));
  }

  /** Submit and wait for the navigation it triggers. The login page uses window.location.href, so
   *  the click tears the page down and its own post-action wait would never settle. */
  async function submitAndNavigate(page: Page) {
    await Promise.all([
      page.waitForURL(/\/dashboard/, { timeout: 20000 }),
      page.getByRole("button", { name: /sign in/i }).click({ noWaitAfter: true }),
    ]);
  }

  async function signIn(page: Page, code: string) {
    await page.goto("/login");
    await dismissConsent(page);
    await page.locator("#email").fill(ADMIN_EMAIL);
    await page.locator("#password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    // Before the fix the admin dead-ended here: 2FA is mandatory for them and the creator login had
    // nowhere to type a code.
    await expect(page.locator("#totp")).toBeVisible();
    await page.locator("#totp").fill(code);
    await submitAndNavigate(page);
  }

  test("an admin with 2FA can complete login on qiko.ai and reach the creator dashboard", async ({ page }) => {
    const errors = trackPageErrors(page);
    const sent: Array<Record<string, unknown>> = [];
    await page.route("**/api/v1/auth/login", async (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      sent.push(body);
      return body.totp ? loggedIn(route) : jsonRoute(route, 401, { detail: "Invalid or missing 2FA code" });
    });
    await stubCreatorSession(page);

    await signIn(page, "123456");  // waits for the /dashboard navigation

    await expect(page).not.toHaveURL(/\/login/);
    expect(sent.map((b) => b.totp)).toEqual([undefined, "123456"]);
    expect(errors).toEqual([]);
  });

  test("the admin lands on the tenant surface, with no cross-tenant admin controls in the creator app", async ({ page }) => {
    await page.route("**/api/v1/auth/login", (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      return body.totp ? loggedIn(route) : jsonRoute(route, 401, { detail: "Invalid or missing 2FA code" });
    });
    await stubCreatorSession(page);

    await signIn(page, "123456");  // waits for the /dashboard navigation

    // Platform administration lives on the admin host behind its own MFA-gated checks. The creator
    // app is the tenant surface and must not surface cross-tenant affordances.
    for (const forbidden of [/all tenants/i, /platform admin/i, /cross-tenant/i]) {
      await expect(page.getByText(forbidden)).toHaveCount(0);
    }
    // Normal creator navigation is available to them.
    await expect(page.getByText(/workers/i).first()).toBeVisible();
  });

  test("an admin who mistypes the code is told what to do and retries without re-entering credentials", async ({ page }) => {
    const sent: Array<Record<string, unknown>> = [];
    await page.route("**/api/v1/auth/login", (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}") as { totp?: string };
      sent.push(body);
      // No code, then a wrong code, then the right one.
      if (body.totp === "123456") return loggedIn(route);
      return jsonRoute(route, 401, { detail: "Invalid or missing 2FA code" });
    });
    await stubCreatorSession(page);

    await page.goto("/login");
    await dismissConsent(page);
    await page.locator("#email").fill(ADMIN_EMAIL);
    await page.locator("#password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.locator("#totp")).toBeVisible();

    await page.locator("#totp").fill("000000");
    await page.getByRole("button", { name: /sign in/i }).click();
    // Stays on the form, mentions backup codes, and does NOT clear what was already typed.
    await expect(page.getByText(/backup code/i).first()).toBeVisible();
    await expect(page.locator("#email")).toHaveValue(ADMIN_EMAIL);
    await expect(page.locator("#password")).toHaveValue(ADMIN_PASSWORD);

    await page.locator("#totp").fill("123456");
    await submitAndNavigate(page);
    expect(sent.map((b) => b.totp)).toEqual([undefined, "000000", "123456"]);
  });

  test("an admin can use a long backup code, not just a 6-digit authenticator code", async ({ page }) => {
    const backupCode = "a1b2c3d4e5f6g7h8";
    const sent: Array<Record<string, unknown>> = [];
    await page.route("**/api/v1/auth/login", (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}") as { totp?: string };
      sent.push(body);
      return body.totp ? loggedIn(route) : jsonRoute(route, 401, { detail: "Invalid or missing 2FA code" });
    });
    await stubCreatorSession(page);

    await page.goto("/login");
    await dismissConsent(page);
    await page.locator("#email").fill(ADMIN_EMAIL);
    await page.locator("#password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.locator("#totp")).toBeVisible();

    await page.locator("#totp").fill(backupCode);
    // The field must not truncate a backup code away via maxLength.
    expect(await page.locator("#totp").inputValue()).toBe(backupCode);
    await submitAndNavigate(page);
    expect(sent.at(-1)?.totp).toBe(backupCode);
  });
});
