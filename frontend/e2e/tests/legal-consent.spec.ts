import { expect, test } from "@playwright/test";

async function dismissConsent(page: any) {
  const reject = page.getByRole("button", { name: "Reject non-essential" }).first();
  if (await reject.isVisible().catch(() => false)) {
    await reject.click().catch(() => {});
    await reject.waitFor({ state: "hidden", timeout: 5000 }).catch(() => {});
  }
}

for (const width of [1440, 390]) {
  test(`CMP and legal pages are usable at ${width}px`, async ({ page }) => {
    let anonymousBody: Record<string, unknown> | undefined;
    await page.route("**/api/v1/consent", (route) => route.fulfill({ status: 401, body: "" }));
    await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 401, body: "" }));
    await page.route("**/api/v1/consent/anonymous", (route) => {
      anonymousBody = route.request().postDataJSON();
      return route.fulfill({ status: 201, contentType: "application/json", body: '{"recorded":true}' });
    });
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.goto("/");
    const banner = page.getByRole("region", { name: "Cookie consent" });
    await expect(banner).toBeVisible();
    await expect(page.getByRole("button", { name: "Accept all" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject non-essential" })).toBeVisible();
    await page.getByRole("button", { name: "Manage preferences" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByLabel("Preferences consent")).toBeVisible();
    await page.getByRole("button", { name: "Reject non-essential" }).last().click();
    await expect(banner).toHaveCount(0);
    await expect.poll(() => anonymousBody).toEqual(expect.objectContaining({
      preferences: false, analytics: false, marketing: false,
    }));
    expect(Object.keys(anonymousBody ?? {}).sort()).toEqual(["analytics", "anonymous_id", "client_revision", "cookies_release_id", "decision_id", "marketing", "preferences", "privacy_release_id", "terms_release_id"]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    for (const path of ["/terms", "/privacy", "/cookies"]) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    }
  });
}

test("invite signup requires clickwrap and routes to email verification", async ({ page }) => {
  let signupBody: Record<string, unknown> | undefined;
  await page.route("**/api/v1/auth/signup", (route) => {
    signupBody = route.request().postDataJSON();
    return route.fulfill({ status: 202, contentType: "application/json", body: '{"verification_required":true}' });
  });
  // Public /signup now redirects to /onboarding. The standalone form remains for invite tokens.
  await page.goto("/signup?invite=test-invite-token");
  await dismissConsent(page);
  const submit = page.getByRole("button", { name: /create account/i });
  await expect(submit).toBeDisabled();
  await page.getByLabel(/I confirm that I am authorised/).check();
  await page.locator("#name").fill("QA User");
  await page.locator("#email").fill("qa" + "@" + "example.test");
  await submit.click();
  await expect.poll(() => signupBody).toEqual(expect.objectContaining({
    accept_policies: true,
    terms_release_id: "terms-2026-07-24",
    privacy_release_id: "privacy-2026-07-24",
    cookies_release_id: "cookies-2026-07-24",
    name: "QA User",
    email: "qa" + "@" + "example.test",
    invite_token: "test-invite-token",
  }));
  expect(signupBody!.password).toBeUndefined();
  await expect(page).toHaveURL(/\/verify-email\?email=/);
});

test("verify email page accepts a six digit code", async ({ page }) => {
  await page.route("**/api/v1/auth/verify-email", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ user_id: "qa", email: "qa" + "@" + "example.test" }) }));
  await page.goto("/verify-email?email=qa%40example.test&code=123456");
  await dismissConsent(page);
  await expect(page.getByLabel("Email")).toHaveValue("qa" + "@" + "example.test");
  await expect(page.getByLabel("Verification code")).toHaveValue("123456");
  await page.getByLabel("Choose password").fill("VerifiedPassword123!");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Verify email" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
