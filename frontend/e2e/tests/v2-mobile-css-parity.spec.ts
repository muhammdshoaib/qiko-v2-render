import { expect, test } from "@playwright/test";

test("landing keeps desktop grids and uses readable mobile snap rows", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const desktopColumns = await page.locator(".q-3col").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(desktopColumns).toBe(3);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const layout = await page.evaluate(() => {
    const hero = document.querySelector<HTMLElement>(".q-hero")!;
    const cards = document.querySelector<HTMLElement>(".q-3col")!;
    const journey = document.querySelector<HTMLElement>(".q-journey")!;
    const infrastructure = document.querySelector<HTMLElement>(".q-4col")!;
    const twoColumn = document.querySelector<HTMLElement>(".q-2col")!;
    const firstSection = document.querySelector<HTMLElement>("main > section")!;
    return {
      documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      heroColumns: getComputedStyle(hero).gridTemplateColumns.split(" ").length,
      cardsDisplay: getComputedStyle(cards).display,
      cardsScrollable: cards.scrollWidth > cards.clientWidth,
      cardWidth: cards.firstElementChild!.getBoundingClientRect().width,
      journeyScrollable: journey.scrollWidth > journey.clientWidth,
      infrastructureScrollable: infrastructure.scrollWidth > infrastructure.clientWidth,
      reportDirection: getComputedStyle(hero.children[1].lastElementChild!.children[1]).flexDirection,
      twoColumnCount: getComputedStyle(twoColumn).gridTemplateColumns.split(" ").length,
      sectionPadding: parseFloat(getComputedStyle(firstSection).paddingLeft),
    };
  });
  expect(layout).toEqual(expect.objectContaining({
    documentFits: true,
    heroColumns: 1,
    cardsDisplay: "flex",
    cardsScrollable: true,
    journeyScrollable: true,
    infrastructureScrollable: true,
    reportDirection: "column",
    twoColumnCount: 1,
    sectionPadding: 16,
  }));
  expect(layout.cardWidth).toBeGreaterThan(260);
});

test("labs contact and CTAs follow tablet and narrow mobile breakpoints", async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 900 });
  await page.goto("/labs");
  const contactColumns = await page.locator("#lb-contact > div:last-child").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(contactColumns).toBe(1);

  await page.setViewportSize({ width: 600, height: 900 });
  await page.reload();
  const cta = page.locator('main[data-labs-page] a[href="#lb-contact"]').first();
  const sectionWidth = await cta.locator("xpath=ancestor::section[1]").evaluate((element) => element.getBoundingClientRect().width);
  const ctaWidth = (await cta.boundingBox())!.width;
  expect(ctaWidth).toBeGreaterThan(sectionWidth - 40);

  await page.setViewportSize({ width: 380, height: 844 });
  await page.reload();
  const narrowFontSize = await cta.evaluate((element) => parseFloat(getComputedStyle(element).fontSize));
  expect(narrowFontSize).toBeGreaterThanOrEqual(13.5);
  expect(narrowFontSize).toBeLessThanOrEqual(13.5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test("login mobile controls meet the 44px touch target", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  const eye = await page.getByRole("button", { name: "Show password" }).boundingBox();
  const submit = await page.getByRole("button", { name: "Sign in" }).boundingBox();
  expect(eye?.width).toBeGreaterThanOrEqual(44);
  expect(eye?.height).toBeGreaterThanOrEqual(44);
  expect(submit?.height).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.reload();
  const desktopEye = await page.getByRole("button", { name: "Show password" }).boundingBox();
  const desktopSubmit = await page.getByRole("button", { name: "Sign in" }).boundingBox();
  expect(desktopEye?.height).toBe(36);
  expect(desktopSubmit?.height).toBe(36);
  await expect(page.getByRole("img", { name: "Qiko" })).toBeVisible();
  await expect(page.getByPlaceholder("you" + "@" + "example.com")).toBeVisible();
});

test("signup and forgot-password fit mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });

  for (const path of ["/signup?invite=test-token", "/forgot-password"]) {
    await page.goto(path);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    const submit = page.getByRole("button").filter({ hasText: /create account|send one-time code/i }).first();
    const box = await submit.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
  }
});

test("onboarding fits mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/onboarding");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

async function mockCreatorSession(page: import("@playwright/test").Page, baseURL: string) {
  await page.context().addCookies([
    { name: "qiko_access", value: "e2e-mobile", url: baseURL },
    { name: "qiko_csrf", value: "e2e-csrf", url: baseURL },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/\/api\/v1/, "");
    const json = (body: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/auth/me") return json({ id: "u1", email: "mobile@example.test", name: "Mobile", role: "owner" });
    if (path === "/consent") return json({ necessary: true, preferences: false, analytics: false, marketing: false });
    if (path === "/agents") return json([]);
    if (path === "/agents/usage") return json({ used: 0, limit: 5, plan: "starter" });
    return json({});
  });
}

test("post-login shell shows mobile header without horizontal overflow", async ({ page, baseURL }) => {
  test.skip(!baseURL, "requires baseURL");
  await mockCreatorSession(page, baseURL!);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("button", { name: "Close menu" }).first()).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
});

test("workers page fits mobile viewport", async ({ page, baseURL }) => {
  test.skip(!baseURL, "requires baseURL");
  await mockCreatorSession(page, baseURL!);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workers");
  await expect(page.getByRole("heading", { name: "Your Workers" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
