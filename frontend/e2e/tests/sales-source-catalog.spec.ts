import { expect, test, type Page } from "@playwright/test";

// Deterministic UI test for the R2 Leg 5d ingestion catalog UI: dynamic source list + catalog add +
// custom-source add + delete. Auth-gated studio route; presence-only cookie + mocked endpoints.

const AGENT_ID = "qa-agent";
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

function tedSource() {
  return {
    id: "src-ted", agentId: AGENT_ID, sourceKey: "ted", name: "TED - EU Tenders", type: "portal",
    status: "active", authStatus: "public_api", scanCadence: "manual", lastScanStatus: null,
    lastScanAt: null, nextScanAt: null, opportunitiesFound: 0, lastError: null,
    config: { url: "https://ted.europa.eu/en/", connector: "ted", scannable: true },
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
  };
}

async function mock(page: Page, posted: string[], deleted: string[]) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (r) => r.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: AGENT_ID, tenant: "qa", name: "QA Sales Worker", status: "ready", atype: "sales_intelligence", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" }]),
  }));
  await page.route("**/api/v1/sales-intelligence/*/opportunities*", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opportunities: [], summary: {} }) }));
  await page.route("**/api/v1/sales-intelligence/*/ingest-filters", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ agentId: AGENT_ID, queryEnabled: true, queryKeyword: "security", allCountries: true, allCategories: true, updatedAt: null }) }));
  // Sources CRUD + catalog on one matcher, branched by method + path.
  await page.route(/\/api\/v1\/sales-intelligence\/[^/]+\/sources(\/[^/]+)?(\?.*)?$/, (route) => {
    const req = route.request();
    const url = req.url();
    const method = req.method();
    if (url.includes("/sources/catalog")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ catalog: [
        { key: "ted", name: "TED - EU Tenders", description: "", type: "portal", authStatus: "public_api", scannable: true, alreadyAdded: true, defaultConfig: { url: "https://ted.europa.eu/en/", apiUrl: null, defaultQuery: "", ingestFilters: null } },
        { key: "ungm", name: "UNGM Public Notices", description: "", type: "portal", authStatus: null, scannable: true, alreadyAdded: false, defaultConfig: { url: "https://www.ungm.org/Public/Notice", apiUrl: null, defaultQuery: "", ingestFilters: null } },
      ] }) });
    }
    if (method === "POST") {
      posted.push(req.postData() ?? "");
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ source: tedSource() }) });
    }
    if (method === "DELETE") {
      deleted.push(url);
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, sourceKey: "ted" }) });
    }
    // GET list (TED scannable + a non-scannable custom source to exercise the scan gate)
    const custom = { ...tedSource(), id: "src-legacy", sourceKey: "legacy-portal", name: "Legacy Portal",
      config: { url: "https://legacy.example", connector: "generic", scannable: false } };
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sources: [tedSource(), custom] }) });
  });
}

test("Ingestion catalog UI: dynamic list, catalog add, custom add, delete", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  const posted: string[] = [];
  const deleted: string[] = [];
  await mock(page, posted, deleted);

  await page.goto(`/studio/${AGENT_ID}/sales-intelligence/ingestion`);
  await page.getByRole("button", { name: "Reject non-essential" }).click();

  // Dynamic list renders the attached TED source card.
  await expect(page.getByText("TED - EU Tenders").first()).toBeVisible();
  // A non-scannable custom source shows the gating hint (its Run Scan is disabled).
  await expect(page.getByText("This source is not yet scannable.")).toBeVisible();

  // Catalog add: UNGM is not-yet-added -> an Add button issues POST {source_key:"ungm"}.
  await page.getByRole("button", { name: /UNGM Public Notices/ }).click();
  await expect.poll(() => posted.some((b) => JSON.parse(b || "{}").source_key === "ungm")).toBe(true);

  // Custom source add: name + url -> POST with slugified key + config.url.
  await page.getByRole("textbox", { name: "Custom source name" }).fill("Acme Portal");
  await page.getByRole("textbox", { name: "Custom source URL" }).fill("https://portal.example/search");
  await page.getByRole("button", { name: /^Add$/ }).click();
  await expect.poll(() => posted.some((b) => {
    const j = JSON.parse(b || "{}");
    return j.source_key === "acme-portal" && j.name === "Acme Portal" && j.config?.url === "https://portal.example/search";
  })).toBe(true);

  // Delete the TED source -> DELETE /sources/ted. Since the delete confirmation modal landed
  // across every Creator delete flow, Remove only opens the dialog; the request fires on Delete.
  await page.getByRole("button", { name: "Remove TED - EU Tenders" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
  await expect.poll(() => deleted.some((u) => /\/sources\/ted(\?|$)/.test(u))).toBe(true);

  expect(pageErrors).toEqual([]);
});
