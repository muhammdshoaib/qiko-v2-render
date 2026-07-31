import { expect, test, type Page } from "@playwright/test";

// Deterministic UI test for the Sales Intelligence pipeline "Rejected & Push Failed" rail
// (R2 Staging parity: tab filter + client-side search + client-side pagination). The studio
// route is auth-gated, but the middleware only checks cookie presence and the page + route
// guard render purely from client fetches, so we pass a session cookie and mock the two
// endpoints the route reads (`/agents` and the opportunities list). No real account or seeded
// data is required; this validates the deployed UI and the rail logic.

const AGENT_ID = "qa-agent";

function makeOpp(id: number, stage: string, title: string, buyer: string) {
  return {
    id, agentId: AGENT_ID, externalId: null, sourceKey: "ted", source: "TED",
    sourceUrl: null, isManual: false, title, buyer, country: "RO", region: null,
    category: "IT", estimatedValue: 100000 + id, currency: "EUR", publishedAt: null,
    deadlineAt: null, stage, recommendation: null, qualificationScore: 42,
    humanReviewStatus: null, reviewedAt: null, assignedReviewerUserId: null,
    assignedReviewerName: null, archivedAt: null, isArchived: false,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
  };
}

// 8 rejected (2 with buyer "Ministry of Testing" for the search assertion) + 3 push_failed
// (=> 11 terminal items, so the default All tab paginates at 6/page) + 2 active.
const OPPORTUNITIES = [
  ...Array.from({ length: 8 }, (_, i) =>
    makeOpp(i + 1, "rejected", `Rejected Tender ${i + 1}`, i < 2 ? "Ministry of Testing" : `Council ${i + 1}`)),
  ...Array.from({ length: 3 }, (_, j) => makeOpp(100 + j, "push_failed", `Push Failed Tender ${j + 1}`, `Agency ${j + 1}`)),
  makeOpp(200, "ingested", "Active Alpha", "Buyer A"),
  makeOpp(201, "qualifying", "Active Beta", "Buyer B"),
];

const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

async function mockPipeline(page: Page) {
  await page.context().addCookies([
    { name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" },
  ]);
  // Keep the client from bouncing to /login: a fake refresh cookie only proves presence, so any
  // stray authenticated 401 would trigger a real refresh that fails and redirects. Stub the token
  // and consent endpoints so the authenticated shell stays rendered for this UI-only test.
  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify([{ id: AGENT_ID, tenant: "qa", name: "QA Sales Worker", status: "ready", atype: "sales_intelligence", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" }]),
    }));
  await page.route("**/api/v1/sales-intelligence/*/opportunities*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opportunities: OPPORTUNITIES, summary: {} }) }));
}

test("Rejected & Push Failed rail supports tab filter, search and pagination", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockPipeline(page);
  await page.goto(`/studio/${AGENT_ID}/sales-intelligence/pipeline`);

  // Dismiss the cookie consent banner so it cannot intercept clicks on the rail controls.
  await page.getByRole("button", { name: "Reject non-essential" }).click();

  await expect(page.getByRole("heading", { name: /Rejected & Push Failed/ })).toBeVisible();

  // Default "All" tab: 11 terminal items, first page of 6.
  await expect(page.getByRole("tab", { name: /All/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText(/Showing 1\u20136 of 11/)).toBeVisible();

  // Pagination: Prev disabled on the first page, next page shows the remaining 5.
  await expect(page.getByRole("button", { name: "Previous page" })).toBeDisabled();
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.getByText(/Showing 7\u201311 of 11/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Next page" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Previous page" })).toBeEnabled();

  // Rejected tab: 8 items, pagination clamps/resets to page 1 (was on page 2 above).
  await page.getByRole("tab", { name: /Rejected/ }).click();
  await expect(page.getByText(/Showing 1\u20136 of 8/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Previous page" })).toBeDisabled();

  // Search narrows client-side (2 rejected items have buyer "Ministry of Testing").
  await page.getByPlaceholder("Search title, buyer or source\u2026").fill("Ministry");
  await expect(page.getByText(/Showing 1\u20132 of 2/)).toBeVisible();

  // Push failed tab: 3 items, single page (no Next control).
  await page.getByPlaceholder("Search title, buyer or source\u2026").fill("");
  await page.getByRole("tab", { name: /Push failed/ }).click();
  await expect(page.getByText(/Showing 1\u20133 of 3/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Next page" })).toHaveCount(0);

  expect(pageErrors).toEqual([]);
});
