import { expect, test, type Page } from "@playwright/test";

// Deterministic UI test for the Sales Intelligence Scan History view (R2 Leg 3, Staging parity).
// Auth-gated studio route rendered from client fetches; we pass a presence-only session cookie and
// mock the endpoints. Asserts the table renders scan entries and that the source/status filters
// issue scan-history requests with the documented source_key/status query params. No real account
// or seeded data is required.

const AGENT_ID = "qa-agent";
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

function entry(id: number, sourceKey: string, status: string) {
  return {
    id, sourceKey, status, opportunitiesFound: status === "success" ? 4 : 0,
    startedAt: "2026-01-01T00:00:00Z", finishedAt: "2026-01-01T00:01:00Z",
    error: status === "failed" ? "connector timeout" : null,
  };
}
const HISTORY = [entry(1, "ted", "success"), entry(2, "ungm", "success"), entry(3, "ted", "failed")];

async function mockScanHistory(page: Page, seen: string[]) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (r) => r.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: AGENT_ID, tenant: "qa", name: "QA Sales Worker", status: "ready", atype: "sales_intelligence", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" }]),
  }));
  await page.route("**/api/v1/sales-intelligence/*/scan-history*", (r) => {
    seen.push(r.request().url());
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ history: HISTORY }) });
  });
}

test("Scan History renders entries and filters issue source_key/status requests", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  const seen: string[] = [];
  await mockScanHistory(page, seen);

  await page.goto(`/studio/${AGENT_ID}/sales-intelligence/scan-history`);
  await page.getByRole("button", { name: "Reject non-essential" }).click();

  // Table renders the three scan entries (one row per entry + header).
  await expect(page.getByRole("cell", { name: "connector timeout" })).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(1 + HISTORY.length);
  await expect.poll(() => seen.some((u) => /scan-history\?.*limit=100/.test(u) || /scan-history\?limit=100/.test(u))).toBe(true);

  // Source filter -> request carries source_key=ted.
  await page.getByRole("button", { name: "TED", exact: true }).click();
  await expect.poll(() => seen.some((u) => /[?&]source_key=ted(&|$)/.test(u))).toBe(true);

  // Status filter -> request carries status=failed.
  await page.getByRole("button", { name: "Failed", exact: true }).click();
  await expect.poll(() => seen.some((u) => /[?&]status=failed(&|$)/.test(u))).toBe(true);

  expect(pageErrors).toEqual([]);
});
