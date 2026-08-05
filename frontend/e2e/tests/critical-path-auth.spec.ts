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

async function dismissConsent(page: Page) {
  const reject = page.getByRole("button", { name: "Reject non-essential" });
  if (await reject.count()) await reject.click().catch(() => {});
}

/** Fail the test on any uncaught page error: an auth screen must never crash. */
function trackPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

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
