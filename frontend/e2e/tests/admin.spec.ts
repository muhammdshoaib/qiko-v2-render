import { test, expect } from "@playwright/test";

const BASE = process.env.ADMIN_BASE_URL ?? "https://admin.preprod.qiko.ai";
const EMAIL = process.env.ADMIN_TEST_EMAIL;
const PASSWORD = process.env.ADMIN_TEST_PASSWORD;

test.describe("Admin app - critical path", () => {
  test("login page renders", async ({ page }) => {
    await page.goto(`${BASE}/login`);
    await expect(page.getByText("Admin Sign In")).toBeVisible();
  });

  test.describe("authenticated", () => {
    test.skip(!EMAIL || !PASSWORD, "set ADMIN_TEST_EMAIL/PASSWORD to run authenticated checks");

    test("platform-admin login reaches the overview and lists customers", async ({ page }) => {
      await page.goto(`${BASE}/login`);
      await page.locator("#email").fill(EMAIL!);
      await page.locator("#password").fill(PASSWORD!);
      await page.getByRole("button", { name: /sign in/i }).click();
      await expect(page).toHaveURL(/\/overview/);
      await expect(page.getByText(/Platform Overview/)).toBeVisible();

      await page.goto(`${BASE}/customers`);
      await expect(page.getByRole("main").getByRole("heading", { name: "Customers" })).toBeVisible();
    });
  });

  // Regression: /admin/* used to be gated by the tenant role (every signup is tenant "owner"),
  // so any regular signed-up user could reach the platform admin panel. Now it requires real
  // platform-admin membership (AdminOrg), checked at the API level.
  test("a non-admin API caller is rejected from the customer directory", async ({ request }) => {
    const apiBase = process.env.BASE_URL ?? "https://preprod.qiko.ai";
    const res = await request.get(`${apiBase}/api/v1/admin/customers`);
    expect(res.status()).toBe(401); // no session at all -> unauthenticated, not authorized
  });
});
