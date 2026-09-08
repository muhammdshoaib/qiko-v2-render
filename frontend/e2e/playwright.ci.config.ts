import { defineConfig, devices } from "@playwright/test";

// CI config for the specs that stub every backend call with page.route(). They need the creator
// app served, nothing else: no preprod, no credentials, no seeded data. That is what makes them
// safe to run on every pull request.
//
// They previously ran only under the manual QA runner in .devin/qa, which had not been used for
// three weeks. In that window three intentional product changes (the delete confirmation modal,
// the Integrations tab rename, a copy rename) moved past their specs and nobody found out until a
// QA run reported ten failures, none of which was a real regression. Running them here turns that
// three-week gap into one pull request.
//
// The origin-dependent specs stay out of this config on purpose. website-parity and the
// legal-consent suite reach a real deployed environment, so they belong to the guarded QA runner
// which enforces the network allowlist.
const PORT = 3100;
const BASE_URL = `http://127.0.0.1:${PORT}`;

// The specs read process.env.BASE_URL directly to build cookie domains, not just Playwright's
// baseURL, so it has to be set before they are imported.
process.env.BASE_URL = BASE_URL;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report-ci" }]],
  outputDir: "test-results-ci",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // The same two viewports the QA catalog requires, so a spec cannot pass here and fail there.
  // The mobile project matters: DataTable renders a card list below md and a table at md and up,
  // and assertions scoped to role=table silently only ever exercised desktop.
  projects: [
    { name: "desktop-1440", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile-390", use: { ...devices["iPhone 13"], browserName: "chromium", viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: `pnpm --filter creator exec next start -p ${PORT}`,
    cwd: "..",
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
