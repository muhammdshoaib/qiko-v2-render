import { expect, test, type Page } from "@playwright/test";

// Deterministic UI test for the opportunity Activity timeline tab (R2 Leg 3b, Staging parity).
// Auth-gated studio route rendered from client fetches; presence-only cookie + mocked endpoints.
// Asserts the Activity tab renders the activity-log timeline from the existing history endpoint.

const AGENT_ID = "qa-agent";
const OPP_ID = 7;
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

const OPPORTUNITY = {
  id: OPP_ID, agentId: AGENT_ID, externalId: null, sourceKey: "ted", source: "TED", sourceUrl: null,
  isManual: false, title: "QA Tender 7", buyer: "Council 7", country: "RO", region: null, category: "IT",
  estimatedValue: 100000, currency: "EUR", publishedAt: null, deadlineAt: null, stage: "qualifying",
  recommendation: null, qualificationScore: 42, humanReviewStatus: null, reviewedAt: null,
  assignedReviewerUserId: null, assignedReviewerName: null, archivedAt: null, isArchived: false,
  createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", detail: null,
};

function log(id: number, action: string, tone: string, detail: string) {
  return {
    id, opportunityId: OPP_ID, actorUserId: 1, actor: { id: 1, userName: "QA Reviewer", email: "qa@example.com" },
    activityType: "opportunity", action, detail, tone, changes: null, metadata: null,
    createdAt: "2026-01-02T09:00:00Z", updatedAt: "2026-01-02T09:00:00Z",
  };
}
const HISTORY = [
  log(3, "reviewer_assigned", "info", "Assigned to QA Reviewer"),
  log(2, "opportunity_qualified", "success", "Auto-qualified by scorer"),
  log(1, "opportunity_created", "info", "Ingested from TED"),
];

async function mockDetail(page: Page) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (r) => r.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: AGENT_ID, tenant: "qa", name: "QA Sales Worker", status: "ready", atype: "sales_intelligence", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" }]),
  }));
  // Single matcher for both the detail and the /history endpoint; branch on the URL.
  await page.route(/\/api\/v1\/sales-intelligence\/[^/]+\/opportunities\/[^/]+(\/history)?(\?.*)?$/, (route) => {
    const url = route.request().url();
    if (/\/history(\?|$)/.test(url)) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opportunityId: OPP_ID, history: HISTORY }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opportunity: OPPORTUNITY }) });
  });
}

test("Opportunity detail Activity tab renders the history timeline", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await mockDetail(page);

  await page.goto(`/studio/${AGENT_ID}/sales-intelligence/pipeline/${OPP_ID}`);
  await page.getByRole("button", { name: "Reject non-essential" }).click();

  await page.getByRole("tab", { name: "Activity" }).click();

  const timeline = page.getByRole("list", { name: "Opportunity activity timeline" });
  await expect(timeline).toBeVisible();
  await expect(timeline.getByText("Reviewer Assigned")).toBeVisible();
  await expect(timeline.getByText("Opportunity Qualified")).toBeVisible();
  await expect(timeline.getByText("Opportunity Created")).toBeVisible();
  await expect(timeline.getByText("Ingested from TED")).toBeVisible();

  expect(pageErrors).toEqual([]);
});
