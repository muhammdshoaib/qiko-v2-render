import { expect, test } from "@playwright/test";

test("later cross-tab withdrawal has a larger client revision", async ({ context }) => {
  const first = await context.newPage();
  const second = await context.newPage();
  const writes: Record<string, unknown>[] = [];
  let releaseAcceptance!: () => void;
  const blocked = new Promise<void>((resolve) => { releaseAcceptance = resolve; });
  for (const page of [first, second]) {
    await page.route("**/api/v1/consent", (route) => route.fulfill({ status: 401, body: "" }));
    await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 401, body: "" }));
    await page.route("**/api/v1/consent/anonymous", async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      writes.push(body);
      if (body.marketing === true) await blocked;
      await route.fulfill({ status: 201, contentType: "application/json", body: '{"recorded":true}' });
    });
  }
  await first.goto("/");
  await second.goto("/");
  await first.getByRole("button", { name: "Accept all" }).click();
  await expect.poll(() => writes.some((write) => write.marketing === true)).toBe(true);
  await second.getByRole("button", { name: "Open cookie settings" }).click();
  await second.getByRole("button", { name: "Reject non-essential" }).click();
  releaseAcceptance();
  await expect.poll(() => writes.some((write) => write.marketing === false)).toBe(true);
  const acceptance = writes.find((write) => write.marketing === true)!;
  const withdrawal = writes.find((write) => write.marketing === false)!;
  expect(Number(withdrawal.client_revision)).toBeGreaterThan(Number(acceptance.client_revision));
});
