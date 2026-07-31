import { expect, test, type Page } from "@playwright/test";

// Deterministic UI test for the Sales Intelligence source enable/disable toggle (R2 Leg 2,
// Staging parity). Auth-gated studio route; middleware checks cookie presence only and the page
// renders from client fetches, so we pass a session cookie and mock the endpoints. We assert the
// per-source switch reflects status and that toggling issues the documented PATCH with the right
// active/inactive status. No real account or seeded data is required.

const AGENT_ID = "qa-agent";
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

function source(sourceKey: string, status: string) {
  return {
    sourceKey, name: sourceKey.toUpperCase(), status, scanCadence: "daily",
    lastScanAt: null, nextScanAt: null, lastScanStatus: null, opportunitiesFound: 0,
  };
}

async function mockIngestion(page: Page) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: AGENT_ID, tenant: "qa", name: "QA Sales Worker", status: "ready", atype: "sales_intelligence", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" }]),
  }));
  await page.route("**/api/v1/sales-intelligence/*/opportunities*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opportunities: [], summary: {} }) }));
  await page.route("**/api/v1/sales-intelligence/*/sources", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sources: [source("ted", "active"), source("ungm", "inactive")] }) }));
}

test("Source cards expose an enable/disable toggle that PATCHes the source status", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await mockIngestion(page);

  // Capture the status PATCH triggered by each toggle (disable TED, enable UNGM).
  const patched: { url: string; body: string }[] = [];
  await page.route("**/api/v1/sales-intelligence/*/sources/ted", (route) => {
    const req = route.request();
    if (req.method() === "PATCH") patched.push({ url: req.url(), body: req.postData() ?? "" });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ source: source("ted", "inactive") }) });
  });
  await page.route("**/api/v1/sales-intelligence/*/sources/ungm", (route) => {
    const req = route.request();
    if (req.method() === "PATCH") patched.push({ url: req.url(), body: req.postData() ?? "" });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ source: source("ungm", "active") }) });
  });

  await page.goto(`/studio/${AGENT_ID}/sales-intelligence/ingestion`);
  await page.getByRole("button", { name: "Reject non-essential" }).click();

  // Active TED source shows a checked switch labelled to disable; inactive UNGM shows unchecked.
  const tedSwitch = page.getByRole("switch", { name: /Disable TED - EU Tenders ingestion/i });
  const ungmSwitch = page.getByRole("switch", { name: /Enable UNGM Public Notices ingestion/i });
  await expect(tedSwitch).toBeVisible();
  await expect(tedSwitch).toHaveAttribute("aria-checked", "true");
  await expect(ungmSwitch).toHaveAttribute("aria-checked", "false");

  // Toggling TED off issues a PATCH with status inactive.
  await tedSwitch.click();
  await expect.poll(() => patched.filter((p) => /\/sources\/ted$/.test(p.url)).length).toBeGreaterThan(0);
  expect(JSON.parse(patched.find((p) => /\/sources\/ted$/.test(p.url))!.body)).toMatchObject({ status: "inactive" });

  // Toggling UNGM on issues a PATCH with status active (enable path).
  await ungmSwitch.click();
  await expect.poll(() => patched.filter((p) => /\/sources\/ungm$/.test(p.url)).length).toBeGreaterThan(0);
  expect(JSON.parse(patched.find((p) => /\/sources\/ungm$/.test(p.url))!.body)).toMatchObject({ status: "active" });

  expect(pageErrors).toEqual([]);
});
