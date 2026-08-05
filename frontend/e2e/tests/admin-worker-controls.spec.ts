import { expect, test, type Page } from "@playwright/test";

// /admin/me returns the effective capability set and the shell filters the nav on it, so mocking
// only `role` would exercise a payload the server never sends.
const ADMIN_CAPABILITIES: Record<"viewer" | "super_admin", string[]> = {
  super_admin: ["view_customers", "manage_customers", "manage_workers", "manage_billing", "manage_admins", "view_ai_cost"],
  viewer: ["view_customers"],
};

async function mockAdmin(page: Page, role: "viewer" | "super_admin") {
  const mutations: unknown[] = [];
  const customerRequests: string[] = [];
  const csrfHeaders: string[] = [];
  const studioRequests: unknown[] = [];
  await page.context().addCookies([
    { name: "qiko_access", value: "test", url: "http://127.0.0.1:3101" },
    { name: "qiko_csrf", value: "csrf-test", url: "http://127.0.0.1:3101" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    const json = (body: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/admin/me")) return json({ role, capabilities: ADMIN_CAPABILITIES[role] });
    if (path.endsWith("/admin/customers") && method === "GET") {
      const url = new URL(route.request().url());
      customerRequests.push(url.search);
      const pageNumber = Number(url.searchParams.get("page") ?? "1");
      return json({ total: 21, page: pageNumber, items: [{ user_id: "acme", email: "owner@invalid", plan: "pro", earnings_cents: 12500 }] });
    }
    if (path.endsWith("/admin/customers/acme") && method === "GET") return json({
      user_id: "acme", email: "owner@invalid", plan: "pro", earnings_cents: 12500, is_studio: true, deleted: false,
      workers: [{ id: "w1", name: "Tender Worker", type: "pre_sales_writer", status: "ready", enabled: true, created_at: "2026-01-01T00:00:00Z", config: {} }],
      worker_state_audit: [{ id: 1, agent_id: "w1", changed_by_email: "admin@invalid", previous_enabled: true, enabled: false, reason: "Contract paused", created_at: "2026-07-01T00:00:00Z" }],
    });
    if (path.endsWith("/studio") && method === "POST") { studioRequests.push(route.request().postDataJSON()); return json({ user_id: "acme", email: "owner@invalid", plan: "pro", earnings_cents: 12500, is_studio: false, deleted: false, workers: [], worker_state_audit: [] }); }
    // The three cross-tenant directories (QIK-515/516/520). Without these branches the catch-all
    // below 404s them, and the nav test navigates through pages that fetch on mount.
    if (path.endsWith("/admin/tenants") && method === "GET") return json({
      total: 1, page: 1, items: [{ tenant_id: "acme", email: "owner@invalid", plan: "pro",
        earnings_cents: 12500, user_count: 3, worker_count: 2, is_studio: true }] });
    if (path.endsWith("/admin/users") && method === "GET") return json({
      total: 1, page: 1, items: [{ id: "u1", email: "owner@invalid", name: "Acme Owner",
        tenant_id: "acme", role: "owner", role_label: "Owner", twofa_enabled: true,
        is_platform_admin: false, platform_role: null, platform_capabilities: [] }] });
    if (path.endsWith("/admin/workers") && method === "GET") return json({
      total: 1, page: 1, items: [{ id: "w1", tenant_id: "acme", name: "Tender Worker",
        type: "pre_sales_writer", status: "ready", enabled: true,
        created_at: "2026-01-01T00:00:00Z", config: {} }] });
    if (path.endsWith("/admin/ai-cost") && method === "GET") return json({
      window_days: 30, totals: { calls: 1, input_tokens: 10, output_tokens: 2,
        cost_nano_usd: 1000000, unpriced_calls: 0 },
      tenant: {}, model: {}, operation: {}, day: {} });
    if (path.endsWith("/admin/worker-monitoring") && method === "GET") return json({
      total: 1, page: 1, window_days: 30, cost_visible: true,
      items: [{ tenant_id: "acme", id: "w1", name: "Tender Worker", status: "ready",
        enabled: true, created_at: "2026-01-01T00:00:00Z", calls: 3,
        last_seen: "2026-08-01T00:00:00Z", cost_nano_usd: 1000000,
        input_tokens: 10, output_tokens: 2 }] });
    if (path.endsWith("/enabled") && method === "PATCH") { mutations.push(route.request().postDataJSON()); csrfHeaders.push(route.request().headers()["x-csrf-token"] ?? ""); return json({ id: "w1", name: "Tender Worker", type: "pre_sales_writer", status: "ready", enabled: false, created_at: "2026-01-01T00:00:00Z", config: {} }); }
    return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"missing mock"}' });
  });
  return { mutations, customerRequests, csrfHeaders, studioRequests };
}

test("Admin login submits the authenticator code", async ({ page }) => {
  let body: unknown;
  await page.route("**/api/v1/auth/login", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ contentType: "application/json", body: '{"user":{}}' });
  });
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@invalid");
  const submittedPassword = ["pass", "word"].join("");
  await page.getByRole("textbox", { name: "Password" }).fill(submittedPassword);
  await page.getByLabel("Authenticator or backup code").fill("123456");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect.poll(() => body).toEqual({ email: "admin@invalid", password: submittedPassword, totp: "123456" });
});

test("super-admin can inspect and confirm worker disable", async ({ page }) => {
  const { mutations, csrfHeaders, studioRequests } = await mockAdmin(page, "super_admin");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/customers");
  const opener = page.getByRole("button", { name: "View details for owner@invalid" });
  await opener.click();
  await expect(page.getByRole("heading", { name: "Customer details" })).toBeVisible();
  await expect(page.getByText("Tender Worker", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Disable Studio" }).click();
  await expect.poll(() => studioRequests).toEqual([{ enabled: false }]);
  await expect(page.getByText(/Enabled to Disabled/)).toBeVisible();
  const toggle = page.getByRole("button", { name: "Disable worker" });
  await toggle.click();
  const confirmation = page.getByRole("dialog", { name: "Confirm disable" });
  await expect(confirmation).toBeVisible();
  await expect(page.getByLabel("Reason (optional)")).toBeFocused();
  for (let index = 0; index < 5; index += 1) await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.querySelector('[aria-labelledby="confirm-worker-title"]')?.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
  await toggle.click();
  await page.getByLabel("Reason (optional)").fill("Maintenance");
  await page.getByRole("button", { name: "Confirm change" }).click();
  await expect.poll(() => mutations.length).toBe(1);
  expect(mutations[0]).toEqual({ enabled: false, reason: "Maintenance" });
  expect(csrfHeaders).toEqual(["csrf-test"]);
  await page.getByRole("button", { name: "Close customer details" }).click();
  await expect(opener).toBeFocused();
});

test("payment links can be listed and created", async ({ page }) => {
  const requests: unknown[] = [];
  await page.context().addCookies([{ name: "qiko_access", value: "test", url: "http://127.0.0.1:3101" }]);
  await page.route("**/api/v1/admin/me", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ role: "super_admin", capabilities: ADMIN_CAPABILITIES.super_admin }) }));
  await page.route("**/api/v1/billing/**", async (route) => {
    const request = route.request();
    if (request.url().includes("payment-links") && request.method() === "POST") requests.push(request.postDataJSON());
    const body = request.url().includes("invoices") ? [] : request.method() === "POST" ? { session_id: "s1", url: "https://pay.invalid/s1", status: "pending" } : [{ session_id: "s1", customer_email: "buyer@invalid", amount_cents: 2500, url: "https://pay.invalid/s1", status: "pending" }];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/invoices");
  await page.getByLabel("Customer email").fill("buyer@invalid");
  await page.getByLabel("Amount").fill("25");
  await page.getByRole("button", { name: "Create link" }).click();
  await expect.poll(() => requests).toEqual([{ customer_email: "buyer@invalid", amount_cents: 2500, recurring: false }]);
  await expect(page.getByRole("link", { name: "Open link" })).toBeVisible();
});

test("search and pagination use server query parameters", async ({ page }) => {
  const { customerRequests } = await mockAdmin(page, "viewer");
  await page.goto("/customers");
  await page.getByLabel("Search customers by email").fill("owner");
  await expect.poll(() => customerRequests.some((query) => query.includes("search=owner"))).toBe(true);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect.poll(() => customerRequests.some((query) => query.includes("page=2"))).toBe(true);
});

test("viewer sees read-only state without mutation controls", async ({ page }) => {
  await mockAdmin(page, "viewer");
  await page.goto("/customers");
  await page.getByRole("button", { name: "View details for owner@invalid" }).click();
  await expect(page.getByText(/Read-only access/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Disable worker" })).toHaveCount(0);
});

test("tablet and mobile navigation expose every Admin destination", async ({ page }) => {
  await mockAdmin(page, "viewer");
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/customers");
  await expect(page.getByRole("link", { name: "Security" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/customers");
  const menu = page.getByRole("button", { name: "Open navigation" });
  await menu.click();
  await expect(page.getByRole("button", { name: "Close menu" })).toBeFocused();
  // One Tab per nav entry plus Sign out. Derived from the label list below rather than hardcoded, so
  // adding a destination cannot silently leave this test asserting the wrong element.
  const MOBILE_NAV_LABELS = ["Overview", "Customers", "Tenants", "Users", "Workers", "Monitoring",
    "AI Cost", "Subscriptions", "Invoices", "Platform Admins", "Analytics", "Security", "Sign out"];
  for (let index = 0; index < MOBILE_NAV_LABELS.length; index += 1) await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.querySelector('[aria-labelledby="mobile-nav-title"]')?.contains(document.activeElement))).toBe(true);
  for (const label of MOBILE_NAV_LABELS) {
    await expect(page.getByText(label, { exact: true }).last()).toBeVisible();
  }
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
});
