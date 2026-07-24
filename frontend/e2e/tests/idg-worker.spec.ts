import { test, expect } from "@playwright/test";

const EMAIL = process.env.IDG_TEST_EMAIL;
const PASSWORD = process.env.IDG_TEST_PASSWORD;

test.describe("IDG worker - grounded answering critical path", () => {
  test.skip(!EMAIL || !PASSWORD, "set IDG_TEST_EMAIL/PASSWORD to run this suite");

  test("Studio shows the IDG worker and answers a grounded research question", async ({ page }) => {
    await page.goto("/login");
    await page.locator("#email").fill(EMAIL!);
    await page.locator("#password").fill(PASSWORD!);
    await page.locator("#password").press("Enter");
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/studio");
    const workerCard = page.getByRole("button", { name: /Pre Sales Writer Worker/i }).first();
    await expect(workerCard).toBeVisible();
    await workerCard.click();

    await page.getByRole("button", { name: "Research", exact: true }).click();
    await page.locator("textarea").fill("Does IDG hold ISO certifications?");
    await page.getByRole("button", { name: /Research \d+ topic/ }).click();

    // Grounded answer with a confidence badge and at least one citation -- proves the answer
    // came from the real imported knowledge base, not a hallucination.
    await expect(page.getByText(/(High confidence|Needs review) · \d+%/)).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(/source\(s\) from the knowledge base/)).toBeVisible();
  });

  test("Studio Overview shows real per-worker metrics and use-case tiles", async ({ page }) => {
    await page.goto("/login");
    await page.locator("#email").fill(EMAIL!);
    await page.locator("#password").fill(PASSWORD!);
    await page.locator("#password").press("Enter");
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/studio");
    await page.getByRole("button", { name: /Pre Sales Writer Worker/i }).first().click();

    // Overview is the default tab: metric tiles + use-case grid (Studio dashboard, SCRUM-70).
    await expect(page.getByText("Active Bids")).toBeVisible();
    await expect(page.getByText("AI Drafting")).toBeVisible();
    await expect(page.getByText("AI Response Generation")).toBeVisible();
    await expect(page.getByText("Compliance Checker")).toBeVisible();
    await expect(page.getByText("Coming soon").first()).toBeVisible();
  });
});
