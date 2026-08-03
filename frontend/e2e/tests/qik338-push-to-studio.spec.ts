import { expect, test, type Page } from "@playwright/test";

// QIK-338: a ready worker can be pushed to Studio via an explicit per-worker flag (config.studio_linked)
// on the worker Settings tab. Auth-gated route rendered from mocked endpoints with a presence-only
// cookie; the config PUT is intercepted, so no real account/data mutation (PUBLIC_READ_ONLY).

const AGENT_ID = "qa-studio";
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

function worker(studioLinked: boolean) {
  return {
    id: AGENT_ID, tenant: "qa", name: "QA Studio Worker", status: "ready",
    atype: "worker", enabled: true, config: studioLinked ? { studio_linked: true } : {},
    created_at: "2026-01-01T00:00:00Z",
  };
}

async function mock(page: Page, put: string[]) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  let linked = false;
  await page.route(/\/api\/v1\/agents\/[^/]+\/config(\?.*)?$/, (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postData() ?? "";
      put.push(body);
      if (JSON.parse(body || "{}").studio_linked === true) linked = true;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(worker(linked)) });
    }
    return route.fallback();
  });
  await page.route(/\/api\/v1\/agents(\?.*)?$/, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([worker(linked)]) }));
  // Anything else the shell touches: harmless empty defaults so the page renders cleanly.
  await page.route(/\/api\/v1\/(knowledge|documents|channels|agents\/[^/]+\/(vapi|salesforce|calendly))[^ ]*/, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
}

test("Settings tab: push a ready worker to Studio", async ({ page }) => {
  const put: string[] = [];
  await mock(page, put);
  await page.goto(`/workers/${AGENT_ID}?tab=Settings`);
  const reject = page.getByRole("button", { name: "Reject non-essential" });
  if (await reject.count()) await reject.click().catch(() => {});

  // Ensure we're on the Settings tab.
  const settingsTab = page.getByRole("button", { name: "Settings" });
  if (await settingsTab.count()) await settingsTab.first().click().catch(() => {});

  const pushBtn = page.getByRole("button", { name: "Push to Studio" });
  await expect(pushBtn).toBeVisible();
  await expect(page.getByText("Not in Studio")).toBeVisible();

  await pushBtn.click();
  await expect.poll(() => put.some((b) => JSON.parse(b || "{}").studio_linked === true)).toBe(true);
  // After the flag flips, the control reflects membership.
  await expect(page.getByRole("button", { name: "Remove from Studio" })).toBeVisible();
});
