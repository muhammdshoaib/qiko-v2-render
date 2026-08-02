import { expect, test } from "@playwright/test";

// QIK-305 regression guard: useAuth now resolves the session via a non-redirecting probe, so an
// ANONYMOUS visitor to the public onboarding / password pages must render them and must NOT be
// bounced to /login (the pre-fix stub + a naive /auth/me call both broke this differently).
// Public, read-only: no auth, no data mutation.

async function dismissConsent(page: import("@playwright/test").Page) {
  const reject = page.getByRole("button", { name: "Reject non-essential" });
  if (await reject.count()) await reject.click().catch(() => {});
}

test("anonymous can open onboarding without being redirected to login", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/onboarding");
  await dismissConsent(page);
  // Stays on onboarding (not kicked to /login) and step 1 renders.
  await expect(page).toHaveURL(/\/onboarding/);
  await expect(page.getByRole("heading", { name: "Choose your industry" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("anonymous can open forgot-password without being redirected to login", async ({ page }) => {
  await page.goto("/forgot-password");
  await dismissConsent(page);
  await expect(page).toHaveURL(/\/forgot-password/);
  await expect(page.locator("#email")).toBeVisible();
});
