import { expect, test } from "@playwright/test";

test("expired authenticated consent fails closed and re-prompts", async ({ page }) => {
  await page.route("**/api/v1/consent", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      decision_id: "auth:expired-accept", client_revision: 1000,
      preferences: true, analytics: true, marketing: true,
      terms_release_id: "terms-2026-07-24", privacy_release_id: "privacy-2026-07-24",
      cookies_release_id: "cookies-2026-07-24", created_at: "2024-01-01T00:00:00.000Z",
    }) });
  });
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Cookie consent" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("qiko.consent.v1"))).toBeNull();
});


test("authenticated server withdrawal overrides stale local acceptance", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("qiko.consent.v1", JSON.stringify({
    schemaVersion: 1, decisionId: "local-accept", revision: 1000, policyVersion: "2026-07-24",
    necessary: true, preferences: true, analytics: true, marketing: true, source: "preferences",
    decidedAt: "2026-07-24T10:00:00.000Z", updatedAt: "2026-07-24T10:00:00.000Z",
    expiresAt: "2027-07-24T10:00:00.000Z", signals: { gpc: false, dnt: false },
  })));
  await page.route("**/api/v1/consent", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      decision_id: "auth:server-withdraw", client_revision: 2000,
      preferences: false, analytics: false, marketing: false,
      terms_release_id: "terms-2026-07-24", privacy_release_id: "privacy-2026-07-24",
      cookies_release_id: "cookies-2026-07-24", created_at: "2026-07-24T11:00:00.000Z",
    }) });
  });
  await page.goto("/");
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("qiko.consent.v1")!).marketing)).toBe(false);
});


test("blocked storage cannot prevent withdrawal cleanup", async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => { throw new DOMException("blocked", "QuotaExceededError"); };
  });
  await page.route("**/api/v1/consent", (route) => route.fulfill({ status: 401, body: "" }));
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 401, body: "" }));
  await page.route("**/api/v1/consent/anonymous", (route) => route.fulfill({
    status: 201, contentType: "application/json", body: '{"recorded":true}' }));
  await page.goto("/");
  await page.getByRole("button", { name: "Reject non-essential" }).click();
  await expect(page.getByRole("region", { name: "Cookie consent" })).toHaveCount(0);
});


test("consent writes preserve user decision order", async ({ page }) => {
  const writes: Record<string, unknown>[] = [];
  let releaseFirst!: () => void;
  const firstBlocked = new Promise<void>((resolve) => { releaseFirst = resolve; });
  await page.route("**/api/v1/consent", (route) => route.fulfill({ status: 401, body: "" }));
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 401, body: "" }));
  await page.route("**/api/v1/consent/anonymous", async (route) => {
    writes.push(route.request().postDataJSON());
    if (writes.length === 1) await firstBlocked;
    await route.fulfill({ status: 201, contentType: "application/json", body: '{"recorded":true}' });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Accept all" }).click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("qiko.consent.pending-sync"))).not.toBeNull();
  await page.getByRole("button", { name: "Open cookie settings" }).click();
  await page.getByRole("button", { name: "Reject non-essential" }).click();
  await expect.poll(() => writes.length).toBe(1);
  releaseFirst();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[0].marketing).toBe(true);
  expect(writes[1].marketing).toBe(false);
});
