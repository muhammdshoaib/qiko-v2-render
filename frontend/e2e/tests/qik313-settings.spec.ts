import { expect, test, type Page } from "@playwright/test";

// QIK-313 full settings: editable profile (name), Billing section (status + link to /billing),
// Integrations section (Teams status + link to workers). Auth-gated route rendered from mocked
// endpoints with a presence-only cookie; the PATCH is intercepted, so no real account/data mutation
// (PUBLIC_READ_ONLY).

const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";

async function mock(page: Page, patched: string[]) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/agents/usage", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ used_count: 0, worker_limit: 3 }) }));
  await page.route("**/api/v1/billing/subscription", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ customer_id: "acme", plan: "pro", status: "active" }) }));
  await page.route("**/api/v1/channels/teams/webhook", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ connected: true, connected_at: "2026-01-01T00:00:00Z" }) }));
  // /auth/me: name starts null (client falls back to email local-part); PATCH captures the new name.
  await page.route("**/api/v1/auth/me", (route) => {
    if (route.request().method() === "PATCH") {
      patched.push(route.request().postData() ?? "");
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: "u1", email: "ronan@qiko.ai", name: "Ronan Bolger", role: "owner" } }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: "u1", email: "ronan@qiko.ai", name: null, role: "owner" } }) });
  });
}

test("Settings: editable profile, billing section, integrations section", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  const patched: string[] = [];
  await mock(page, patched);

  await page.goto("/settings");
  const reject = page.getByRole("button", { name: "Reject non-essential" });
  if (await reject.count()) await reject.click().catch(() => {});

  // Profile: name field seeded from the email local-part when name is null.
  const nameInput = page.getByLabel("Name");
  await expect(nameInput).toBeVisible();
  await expect(nameInput).toHaveValue("ronan");
  await expect(page.getByText("ronan@qiko.ai")).toBeVisible();

  // Edit + save -> PATCH /auth/me with the new name.
  await nameInput.fill("Ronan Bolger");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect.poll(() => patched.some((b) => JSON.parse(b || "{}").name === "Ronan Bolger")).toBe(true);

  // Billing section: shows current plan + a Manage billing action.
  await expect(page.getByText("Current plan:")).toBeVisible();
  await expect(page.getByRole("button", { name: /Manage billing/ })).toBeVisible();

  // Integrations section: Teams status + manage worker connections.
  await expect(page.getByText("Microsoft Teams notifications")).toBeVisible();
  await expect(page.getByRole("button", { name: /Manage worker connections/ })).toBeVisible();

  expect(pageErrors).toEqual([]);
});
