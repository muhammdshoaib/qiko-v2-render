import { defineConfig } from "@playwright/test";

const localRun = process.env.QIKO_LOCAL === "1";

function localHttpPort(): string {
  const value = process.env.QIKO_DEV_HTTP_PORT ?? "8080";
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535) {
    throw new Error("QIKO_DEV_HTTP_PORT must be an integer between 1 and 65535.");
  }
  return value;
}

const port = localRun ? localHttpPort() : null;
const localCreatorBaseURL = port ? `http://qiko.localhost:${port}` : null;
const localAdminBaseURL = port ? `http://admin.qiko.localhost:${port}` : null;

if (localRun) {
  process.env.BASE_URL = localCreatorBaseURL!;
  process.env.ADMIN_BASE_URL = localAdminBaseURL!;
}

// Critical-path smoke tests against a live environment (defaults to preprod). Run with:
//   BASE_URL=https://preprod.qiko.ai ADMIN_BASE_URL=https://admin.preprod.qiko.ai npx playwright test
export default defineConfig({
  testDir: "./tests",
  fullyParallel: !localRun,
  workers: localRun ? 1 : undefined,
  retries: localRun ? 0 : process.env.CI ? 2 : 0,
  reporter: localRun ? [["list"]] : [["list"], ["html", { open: "never" }]],
  outputDir: localRun ? "test-results/local" : "test-results",
  metadata: {
    adminBaseURL: localAdminBaseURL ?? process.env.ADMIN_BASE_URL ?? "https://admin.preprod.qiko.ai",
  },
  use: {
    baseURL: localCreatorBaseURL ?? process.env.BASE_URL ?? "https://preprod.qiko.ai",
    serviceWorkers: localRun ? "block" : "allow",
    trace: localRun ? "off" : "retain-on-failure",
    screenshot: localRun ? "off" : "only-on-failure",
  },
});
