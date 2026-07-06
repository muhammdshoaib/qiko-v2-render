import { defineConfig } from "@playwright/test";

// Critical-path smoke tests against a live environment (defaults to preprod). Run with:
//   BASE_URL=https://preprod.qiko.ai ADMIN_BASE_URL=https://admin.preprod.qiko.ai npx playwright test
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.BASE_URL ?? "https://preprod.qiko.ai",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
