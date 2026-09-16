import { expect, test, type Page } from "@playwright/test";

// IDG-1008: the cockpit chat opens as an overlay on desktop and its width is draggable from the
// left edge, clamped, and remembered across reloads. Deterministic: the studio route renders from
// client fetches, so a presence-only session cookie plus mocked endpoints is enough. No real
// account or seeded data.

const AGENT_ID = "qa-agent";
const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";
const MIN_WIDTH = 300;
const MAX_WIDTH = 720;

async function mockCockpit(page: Page) {
  await page.context().addCookies([{ name: "qiko_refresh", value: "e2e", domain: new URL(BASE_URL).hostname, path: "/" }]);
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/consent**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/agents", (r) => r.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: AGENT_ID, tenant: "qa", name: "QA Sales Worker", status: "ready", atype: "sales_intelligence", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" }]),
  }));
  await page.route("**/api/v1/sales-intelligence/*/opportunities*", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opportunities: [], summary: {} }) }));
  await page.route("**/api/v1/sales-intelligence/*/sources", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sources: [] }) }));
  await page.route("**/api/v1/notifications**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ notifications: [], unreadCount: 0 }) }));
}

async function openCockpit(page: Page) {
  await page.goto(`/studio/${AGENT_ID}/sales-intelligence`);
  await page.getByRole("button", { name: "Reject non-essential" }).click();
}

function panel(page: Page) {
  return page.getByRole("complementary").filter({ has: page.getByRole("separator", { name: "Resize chat panel" }) });
}

async function panelWidth(page: Page): Promise<number> {
  const box = await panel(page).boundingBox();
  return box?.width ?? 0;
}

test.describe("cockpit chat resize", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 1024, "resize handle is desktop-only");

  test("chat opens closed, then drags wider from its left edge and remembers the width", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));
    await mockCockpit(page);
    await openCockpit(page);

    // Closed on arrival (IDG-1007): an open overlay would cover the content.
    await expect(page.getByRole("separator", { name: "Resize chat panel" })).toHaveCount(0);

    await page.getByRole("button", { name: "Toggle chat panel" }).click();
    const handle = page.getByRole("separator", { name: "Resize chat panel" });
    await expect(handle).toBeVisible();
    const startWidth = await panelWidth(page);
    expect(startWidth).toBeGreaterThanOrEqual(MIN_WIDTH);

    // Drag the edge 120px to the left: anchored right, so the panel gets wider.
    const box = await handle.boundingBox();
    if (!box) throw new Error("resize handle has no box");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 120, box.y + box.height / 2, { steps: 12 });
    await page.mouse.up();

    const widened = await panelWidth(page);
    expect(widened).toBeGreaterThan(startWidth + 80);
    await expect(handle).toHaveAttribute("aria-valuenow", String(Math.round(widened)));

    // Remembered: reopening after a reload restores the dragged width, not the default.
    await page.reload();
    await page.getByRole("button", { name: "Toggle chat panel" }).click();
    await expect(page.getByRole("separator", { name: "Resize chat panel" })).toBeVisible();
    expect(Math.abs((await panelWidth(page)) - widened)).toBeLessThanOrEqual(2);

    expect(pageErrors).toEqual([]);
  });

  test("width is clamped and the handle is keyboard operable", async ({ page }) => {
    await mockCockpit(page);
    await openCockpit(page);
    await page.getByRole("button", { name: "Toggle chat panel" }).click();

    const handle = page.getByRole("separator", { name: "Resize chat panel" });
    await expect(handle).toHaveAttribute("aria-valuemin", String(MIN_WIDTH));
    await expect(handle).toHaveAttribute("aria-valuemax", String(MAX_WIDTH));

    // Keyboard: ArrowLeft widens (the panel grows leftwards), ArrowRight narrows.
    const before = await panelWidth(page);
    await handle.focus();
    await page.keyboard.press("ArrowLeft");
    expect(await panelWidth(page)).toBeGreaterThan(before);
    await page.keyboard.press("ArrowRight");
    expect(Math.abs((await panelWidth(page)) - before)).toBeLessThanOrEqual(2);

    // Far beyond the maximum in one drag: clamped, never wider than MAX_WIDTH.
    const box = await handle.boundingBox();
    if (!box) throw new Error("resize handle has no box");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(10, box.y + box.height / 2, { steps: 10 });
    await page.mouse.up();
    expect(await panelWidth(page)).toBeLessThanOrEqual(MAX_WIDTH);

    // And far past the minimum the other way.
    const handleAfter = await handle.boundingBox();
    if (!handleAfter) throw new Error("resize handle has no box");
    await page.mouse.move(handleAfter.x + handleAfter.width / 2, handleAfter.y + handleAfter.height / 2);
    await page.mouse.down();
    await page.mouse.move(page.viewportSize()!.width - 10, handleAfter.y + handleAfter.height / 2, { steps: 10 });
    await page.mouse.up();
    expect(await panelWidth(page)).toBeGreaterThanOrEqual(MIN_WIDTH);
  });
});
