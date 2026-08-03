import { expect, test, type Page } from "@playwright/test";

// QIK-338: a ready worker can be pushed to Studio via an explicit per-worker flag (config.studio_linked)
// on the worker Settings tab. Auth-gated route rendered from mocked endpoints with a presence-only
// cookie; the config PUT is intercepted, so no real account/data mutation (PUBLIC_READ_ONLY).

const AGENT_ID = "qa-studio";
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

function makeWorker(status: string, studioLinked: boolean) {
  return {
    id: AGENT_ID, tenant: "qa", name: "QA Studio Worker", status,
    atype: "worker", enabled: true, config: studioLinked ? { studio_linked: true } : {},
    created_at: "2026-01-01T00:00:00Z",
  };
}

// updateAgentConfig posts { patch: {...} }, so the flag lives at body.patch.studio_linked.
const patchFlag = (body: string) => JSON.parse(body || "{}").patch?.studio_linked;

async function mock(page: Page, put: string[], status = "ready") {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  let linked = false;
  // Playwright matches the LAST-registered route first, so register the broad catch-all FIRST and the
  // specific routes AFTER (specifics win; the catch-all keeps the heavy worker page from hanging).
  await page.route(/\/api\/v1\/.*/, (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/auth/me", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: "u1", email: "qa@qiko.ai", name: null, role: "owner" } }) }));
  await page.route(/\/api\/v1\/agents\/usage(\?.*)?$/, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ used_count: 1, worker_limit: 3 }) }));
  await page.route(/\/api\/v1\/agents\/[^/]+\/config(\?.*)?$/, (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postData() ?? "";
      put.push(body);
      if (patchFlag(body) === true) linked = true;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(makeWorker(status, linked)) });
    }
    return route.fallback();
  });
  // Registered last => highest precedence for the plain agents-list endpoint.
  await page.route(/\/api\/v1\/agents(\?.*)?$/, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([makeWorker(status, linked)]) }));
}

async function openSettings(page: Page) {
  await page.goto(`/workers/${AGENT_ID}?tab=Settings`);
  const reject = page.getByRole("button", { name: "Reject non-essential" });
  if (await reject.count()) await reject.click().catch(() => {});
  const settingsTab = page.getByRole("button", { name: "Settings" });
  if (await settingsTab.count()) await settingsTab.first().click().catch(() => {});
}

test("Settings tab: push a ready worker to Studio", async ({ page }) => {
  const put: string[] = [];
  await mock(page, put, "ready");
  await openSettings(page);

  const pushBtn = page.getByRole("button", { name: "Push to Studio" });
  await expect(pushBtn).toBeVisible();
  await expect(page.getByText("Not in Studio")).toBeVisible();

  await pushBtn.click();
  await expect.poll(() => put.some((b) => patchFlag(b) === true)).toBe(true);
  await expect(page.getByRole("button", { name: "Remove from Studio" })).toBeVisible();
});

test("Push to Studio is disabled until the worker is ready", async ({ page }) => {
  const put: string[] = [];
  await mock(page, put, "training");
  await openSettings(page);

  const pushBtn = page.getByRole("button", { name: "Push to Studio" });
  await expect(pushBtn).toBeVisible();
  await expect(pushBtn).toBeDisabled();
  expect(put).toHaveLength(0);
});
