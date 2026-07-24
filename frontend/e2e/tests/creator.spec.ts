import { test, expect } from "@playwright/test";

const EMAIL = process.env.CREATOR_TEST_EMAIL;
const PASSWORD = process.env.CREATOR_TEST_PASSWORD;
const RUN_PASSWORD_RESET_ACCEPTANCE = process.env.RUN_PASSWORD_RESET_ACCEPTANCE === "1";

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

  test("forgot response still reaches reset form when sessionStorage is blocked", async ({ page }) => {
    test.skip(!RUN_PASSWORD_RESET_ACCEPTANCE, "set RUN_PASSWORD_RESET_ACCEPTANCE=1 after deployment");
    await page.addInitScript(() => {
      Object.defineProperty(window, "sessionStorage", {
        configurable: true,
        get() {
          throw new DOMException("Blocked for acceptance test", "SecurityError");
        },
      });
    });
    await page.route("**/api/v1/auth/forgot-password", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sent: true }) });
    });

    await page.goto("/forgot-password");
    await page.locator("#email").fill(" Storage.Blocked@Example.Test ");
    await page.getByRole("button", { name: "Send reset link" }).click();

    await expect(page).toHaveURL(/\/reset-password\?email=storage\.blocked%40example\.test$/);
    await expect(page.getByText(
      "We have sent a one-time code to the provided email address. Please check your email and enter the code below.",
    )).toBeVisible();
    await expect(page.locator("#email")).toHaveValue("storage.blocked@example.test");
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
