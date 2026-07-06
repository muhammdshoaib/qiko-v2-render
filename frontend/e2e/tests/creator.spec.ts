import { test, expect } from "@playwright/test";

const EMAIL = process.env.CREATOR_TEST_EMAIL;
const PASSWORD = process.env.CREATOR_TEST_PASSWORD;

test.describe("Creator app - critical path", () => {
  test("landing page loads with the real brand", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/Qiko/);
    await expect(page.locator("nav")).toBeVisible();
  });

  test("login page renders the auth card", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Welcome back")).toBeVisible();
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
  });

  test.describe("authenticated", () => {
    test.skip(!EMAIL || !PASSWORD, "set CREATOR_TEST_EMAIL/PASSWORD to run authenticated checks");
    // Single-session revocation: logging in again rotates the sid and invalidates any other
    // concurrent session for the same account, so these must not run in parallel against it.
    test.describe.configure({ mode: "serial" });

    test("login -> dashboard -> sign-out round trip", async ({ page }) => {
      await page.goto("/login");
      await page.locator("#email").fill(EMAIL!);
      await page.locator("#password").fill(PASSWORD!);
      await page.locator("#password").press("Enter");
      await expect(page).toHaveURL(/\/dashboard/);

      // Regression: sign-out used to fail silently (missing CSRF header) and leave the user stuck.
      const signOut = page.getByRole("button", { name: /sign out/i });
      await signOut.click();
      await expect(page).toHaveURL(/\/login/);
    });

    test("Studio surfaces published workers", async ({ page }) => {
      await page.goto("/login");
      await page.locator("#email").fill(EMAIL!);
      await page.locator("#password").fill(PASSWORD!);
      await page.locator("#password").press("Enter");
      await expect(page).toHaveURL(/\/dashboard/);

      await page.goto("/studio");
      await expect(page.getByText(/active/)).toBeVisible();
    });
  });
});
