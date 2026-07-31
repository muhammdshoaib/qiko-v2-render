import { expect, test, type Page } from "@playwright/test";

// Deterministic UI test for persisted ingest filters (R2 backend leg, Staging parity). Auth-gated
// studio route rendered from client fetches; presence-only cookie + mocked endpoints. Asserts the
// saved filter seeds the controls on load and that Save issues the PATCH with the field values.

const AGENT_ID = "qa-agent";
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

async function mockIngestion(page: Page, patched: string[]) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (r) => r.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: AGENT_ID, tenant: "qa", name: "QA Sales Worker", status: "ready", atype: "sales_intelligence", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" }]),
  }));
  await page.route("**/api/v1/sales-intelligence/*/opportunities*", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opportunities: [], summary: {} }) }));
  await page.route("**/api/v1/sales-intelligence/*/sources", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sources: [] }) }));
  // Persisted ingest filter: GET returns a saved value; PATCH is captured.
  await page.route("**/api/v1/sales-intelligence/*/ingest-filters", (route) => {
    const req = route.request();
    if (req.method() === "PATCH") {
      patched.push(req.postData() ?? "");
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ agentId: AGENT_ID, queryEnabled: true, queryKeyword: "guard services", allCountries: true, allCategories: false, updatedAt: "2026-01-02T00:00:00Z" }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ agentId: AGENT_ID, queryEnabled: true, queryKeyword: "guard services", allCountries: true, allCategories: false, updatedAt: null }) });
  });
}

test("Ingest filters seed from the saved setting and Save persists them", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  const patched: string[] = [];
  await mockIngestion(page, patched);

  await page.goto(`/studio/${AGENT_ID}/sales-intelligence/ingestion`);
  await page.getByRole("button", { name: "Reject non-essential" }).click();

  // The saved keyword seeds the Portal query input.
  await expect(page.getByRole("textbox", { name: "Portal query keyword" })).toHaveValue("guard services");

  // Save issues a PATCH carrying the current filter values.
  await page.getByRole("button", { name: /Save filters/ }).click();
  await expect.poll(() => patched.length).toBeGreaterThan(0);
  const body = JSON.parse(patched[0]);
  expect(body).toMatchObject({ query_keyword: "guard services", query_enabled: true });
  expect(body).toHaveProperty("all_countries");
  expect(body).toHaveProperty("all_categories");

  expect(pageErrors).toEqual([]);
});
