import { expect, test, type Page } from "@playwright/test";

async function mockPublicApi(page: Page) {
  await page.route("**/api/v1/consent**", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ recorded: true }) });
  });
  await page.route("**/api/v1/billing/plans", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.context().route(/^https:\/\/qiko\.ai\/signal(?:\/|$|\?)/, (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<title>Qiko Signal</title>" }));
}

for (const viewport of [{ name: "desktop", width: 1440, height: 900 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`Signal navigation remains unchanged on ${viewport.name}`, async ({ page }, testInfo) => {
    const analyticsRequests: string[] = [];
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("request", (request) => {
      if (request.url().includes("cloudflareinsights")) analyticsRequests.push(request.url());
    });
    await mockPublicApi(page);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/");
    await page.getByRole("button", { name: "Reject non-essential" }).click();
    await expect(page.locator('script[src*="cloudflareinsights"]')).toHaveCount(0);
    expect(analyticsRequests).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

    if (viewport.name === "desktop") {
      const signalMenu = page.locator("header").getByRole("button", { name: /^Signal/ }).first();
      await expect(signalMenu).toBeVisible();
      await expect(page.getByText("Coming Soon", { exact: true })).toHaveCount(0);
      await signalMenu.focus();
      const overview = page.getByRole("button", { name: "Overview" }).first();
      await overview.focus();
      const popupPromise = page.waitForEvent("popup");
      await overview.press("Enter");
      const popup = await popupPromise;
      await expect(popup).toHaveURL(/^https:\/\/qiko\.ai\/signal(?:\/|$)/);
      await popup.close();
      const labsMenu = page.locator("header").getByRole("button", { name: /^Labs/ }).first();
      await labsMenu.focus();
      await expect(labsMenu).toHaveAttribute("aria-expanded", "true");
      await labsMenu.press("Escape");
      await expect(labsMenu).toHaveAttribute("aria-expanded", "false");
    } else {
      await page.getByRole("button", { name: "Menu" }).click();
      await expect(page.getByText("Coming Soon", { exact: true })).toHaveCount(0);
      for (const name of [/^Home$/, /^Signal$/, /^Labs$/, /^About$/, /^Sign in$/, /Get started/]) {
        const control = page.locator("header").getByRole("button", { name }).last();
        const box = await control.boundingBox();
        expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
      }
      const mobileSignal = page.locator("header").getByRole("button", { name: "Signal", exact: true }).last();
      await mobileSignal.focus();
      const popupPromise = page.waitForEvent("popup");
      await mobileSignal.press("Enter");
      const popup = await popupPromise;
      await expect(popup).toHaveURL(/^https:\/\/qiko\.ai\/signal(?:\/|$)/);
      await popup.close();
    }

    await expect(page).toHaveURL(/\/$/);
    await page.screenshot({ path: testInfo.outputPath(`website-${viewport.name}.png`), fullPage: true });
    expect(consoleErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
}

test("security.txt is publicly accessible without authentication", async ({ page }) => {
  const response = await page.goto("/.well-known/security.txt");
  expect(response?.status()).toBe(200);
  await expect(page.locator("body")).toContainText("Contact: mailto:support" + "@" + "qiko.ai");
  await expect(page).toHaveURL(/\/\.well-known\/security\.txt$/);
});

test("required public routes render without browser errors", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockPublicApi(page);
  for (const route of ["/", "/labs", "/terms", "/privacy", "/cookies", "/login", "/onboarding"]) {
    const response = await page.goto(route);
    expect(response?.status()).toBe(200);
    await expect(page.locator("body")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
