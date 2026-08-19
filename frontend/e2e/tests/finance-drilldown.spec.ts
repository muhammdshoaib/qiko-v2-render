import { expect, test, type Page } from "@playwright/test";

// Deterministic UI test for the Financial Analyst drilldown dashboard.
// The finance routes are auth-gated, but the middleware only checks cookie presence and the
// client routes fetch their own data, so we pass a presence-only refresh cookie and mock all
// backend endpoints. No real account or seeded data is required.

const AGENT_ID = "qa-financial-analyst";

const BASE_URL = process.env.BASE_URL ?? "https://preprod.qiko.ai";
const COOKIE_HOST = new URL(BASE_URL).hostname;

const MONTHLY_TRENDS = [
  { month: "2025-01", income: 20000, expenses: 8000, netProfit: 12000 },
  { month: "2025-02", income: 21000, expenses: 9000, netProfit: 12000 },
];

const EXPENSES_A_101 = [
  { heading: "Utilities", expenditureDescription: "Electricity", supplierName: "City Utilities", nett: 12000, vat: 2400, gross: 14400, invoiceDate: "2025-01-15", settled: "yes" },
  { heading: "Maintenance", expenditureDescription: "Lift service", supplierName: "Acme Maintenance", nett: 20000, vat: 4000, gross: 24000, invoiceDate: "2025-02-10", settled: "yes" },
];

const EXPENSES_A_102 = [
  { heading: "Utilities", expenditureDescription: "Water", supplierName: "City Utilities", nett: 3000, vat: 600, gross: 3600, invoiceDate: "2025-02-05", settled: "no" },
  { heading: "Cleaning", expenditureDescription: "Office cleaning", supplierName: "Clean Team", nett: 5000, vat: 1000, gross: 6000, invoiceDate: "2025-01-20", settled: "yes" },
];

const EXPENSES_B_101 = [
  { heading: "Maintenance", expenditureDescription: "Roof repair", supplierName: "Acme Maintenance", nett: 30000, vat: 6000, gross: 36000, invoiceDate: "2025-01-18", settled: "yes" },
  { heading: "Insurance", expenditureDescription: "Buildings insurance", supplierName: "InsureCo", nett: 12000, vat: 0, gross: 12000, invoiceDate: "2025-01-22", settled: "yes" },
];

const PROPERTY_A = {
  propertyId: "A001",
  propertyRef: "A001",
  name: "Avenue House",
  income: 150000,
  expenses: 48000,
  netProfit: 102000,
  marginPercent: 68,
  outstanding: 10000,
  costToIncomeRatio: 32,
  riskScore: 25,
  riskLevel: "low",
  profitabilityClass: "high-performing",
  invoiceCount: 4,
  vendorCount: 3,
  unitCount: 2,
  expenseCategories: [
    { category: "Utilities", amount: 15000 },
    { category: "Maintenance", amount: 20000 },
    { category: "Cleaning", amount: 5000 },
  ],
  topVendors: [
    { vendorName: "Acme Maintenance", amount: 20000 },
    { vendorName: "City Utilities", amount: 15000 },
    { vendorName: "Clean Team", amount: 5000 },
  ],
  monthlyTrends: MONTHLY_TRENDS,
  unitLedger: [
    {
      unitRef: "101",
      unitDescription: "Ground floor office",
      propertyRef: "A001",
      propertyName: "Avenue House",
      income: 80000,
      outstanding: 5000,
      totalGross: 38400,
      totalNett: 32000,
      totalVat: 6400,
      netProfit: 50000,
      invoiceCount: 2,
      vendorCount: 2,
      expenses: EXPENSES_A_101,
    },
    {
      unitRef: "102",
      unitDescription: "First floor suite",
      propertyRef: "A001",
      propertyName: "Avenue House",
      income: 70000,
      outstanding: 5000,
      totalGross: 9600,
      totalNett: 8000,
      totalVat: 1600,
      netProfit: 60000,
      invoiceCount: 2,
      vendorCount: 2,
      expenses: EXPENSES_A_102,
    },
  ],
};

const PROPERTY_B = {
  propertyId: "B002",
  propertyRef: "B002",
  name: "Baker Street",
  income: 100000,
  expenses: 52000,
  netProfit: 48000,
  marginPercent: 48,
  outstanding: 10000,
  costToIncomeRatio: 52,
  riskScore: 85,
  riskLevel: "high",
  profitabilityClass: "loss-making",
  invoiceCount: 2,
  vendorCount: 2,
  unitCount: 1,
  expenseCategories: [
    { category: "Maintenance", amount: 30000 },
    { category: "Insurance", amount: 12000 },
  ],
  topVendors: [
    { vendorName: "Acme Maintenance", amount: 30000 },
    { vendorName: "InsureCo", amount: 12000 },
  ],
  monthlyTrends: MONTHLY_TRENDS,
  unitLedger: [
    {
      unitRef: "B101",
      unitDescription: "Basement archive",
      propertyRef: "B002",
      propertyName: "Baker Street",
      income: 100000,
      outstanding: 10000,
      totalGross: 48000,
      totalNett: 42000,
      totalVat: 6000,
      netProfit: 48000,
      invoiceCount: 2,
      vendorCount: 2,
      expenses: EXPENSES_B_101,
    },
  ],
};

const ANALYTICS = {
  status: "ok",
  totalFiles: 1,
  totalRows: 100,
  currency: "GBP",
  dateRange: { from: "2025-01-01", to: "2025-12-31", label: "2025" },
  summary: {
    totalIncome: 250000,
    totalExpenses: 100000,
    netProfit: 150000,
    outstanding: 20000,
    propertyCount: 2,
    vendorCount: 4,
  },
  properties: [PROPERTY_A, PROPERTY_B],
  charts: {},
  insights: {},
  trends: [{ section: "Portfolio", title: "Portfolio overview", insights: [{ title: "Top performer", text: "Avenue House is the top performer." }] }],
};

const FILES = {
  files: [{ id: "file-1", label: "portfolio-2025.xlsx", namespace: "ns-1", rowCount: 100, uploadedAt: "2025-01-01T00:00:00Z" }],
  totalFiles: 1,
  totalRows: 100,
};

const AGENTS = [
  { id: AGENT_ID, tenant: "qa", name: "QA Financial Analyst", status: "ready", atype: "finance", enabled: true, config: {}, created_at: "2026-01-01T00:00:00Z" },
];

function analyticsUrl() {
  return new RegExp(`.*/api/v1/finance/${AGENT_ID}/analytics(\\?.*)?$`);
}

function financeFilesUrl() {
  return new RegExp(`.*/api/v1/finance/${AGENT_ID}/files(\\?.*)?$`);
}

function financeHistoryUrl() {
  return new RegExp(`.*/api/v1/finance/${AGENT_ID}/history(\\?.*)?$`);
}

async function dismissConsent(page: Page) {
  const btn = page.getByRole("button", { name: "Reject non-essential" });
  const count = await btn.count();
  if (count > 0 && await btn.isVisible()) await btn.click();
}

async function mockFinanceApis(page: Page) {
  await page.context().addCookies([
    { name: "qiko_refresh", value: "e2e", domain: COOKIE_HOST, path: "/" },
  ]);
  await page.route(/.*\/api\/v1\/auth\/refresh/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route(/.*\/api\/v1\/consent/, (route) =>
    route.fulfill({ status: 204, body: "" }));
  await page.route(/.*\/api\/v1\/agents$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(AGENTS) }));
  await page.route(analyticsUrl(), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ANALYTICS) }));
  await page.route(financeFilesUrl(), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FILES) }));
  await page.route(financeHistoryUrl(), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, history: [] }) }));
}

test.describe("Finance drilldown dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await mockFinanceApis(page);
  });

  test("KPI cards and charts route to breakdown, vendor, expenditure and property pages", async ({ page }) => {
    await page.goto(`/studio/${AGENT_ID}/finance`);
    await dismissConsent(page);

    await expect(page.getByText("QA Financial Analyst").first()).toBeVisible();
    await expect(page.getByText("Total Income").first()).toBeVisible();

    await page.getByRole("button", { name: /Total Properties/ }).click();
    await expect(page).toHaveURL(new RegExp(`https?://[^/]+/studio/${AGENT_ID}/finance/breakdown\\?view=properties`));
    await expect(page.getByRole("heading", { name: "Portfolio properties" }).first()).toBeVisible();

    await page.getByRole("table", { name: "Portfolio properties" }).getByRole("button", { name: /Avenue House/ }).click();
    await expect(page).toHaveURL(new RegExp(`https?://[^/]+/studio/${AGENT_ID}/finance/property/A001`));
    await expect(page.getByRole("heading", { name: "Avenue House" })).toBeVisible();

    await page.goto(`/studio/${AGENT_ID}/finance`);
    await dismissConsent(page);

    await page.getByRole("button", { name: /^Acme Maintenance/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`https?://[^/]+/studio/${AGENT_ID}/finance/vendor/Acme%20Maintenance`));
    await expect(page.getByRole("heading", { name: "Acme Maintenance" })).toBeVisible();

    await page.goto(`/studio/${AGENT_ID}/finance`);
    await dismissConsent(page);

    await page.getByRole("button", { name: /^Utilities$/ }).click();
    await expect(page).toHaveURL(new RegExp(`https?://[^/]+/studio/${AGENT_ID}/finance/expenditure\\?category=Utilities`));
    await expect(page.getByRole("heading", { name: /Expense category/ })).toBeVisible();
    await expect(page.getByText("2 expense rows")).toBeVisible();

    await page.goto(`/studio/${AGENT_ID}/finance`);
    await dismissConsent(page);

    await page.getByRole("button", { name: /^Baker Street/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`https?://[^/]+/studio/${AGENT_ID}/finance/property/B002`));
    await expect(page.getByRole("heading", { name: "Baker Street" })).toBeVisible();
  });

  test("Property detail shows unit ledger and unit expenses", async ({ page }) => {
    await page.goto(`/studio/${AGENT_ID}/finance/property/A001`);
    await dismissConsent(page);

    await expect(page.getByRole("heading", { name: "Avenue House" })).toBeVisible();
    await expect(page.getByRole("table", { name: /Units for Avenue House/ }).getByText("Ground floor office").first()).toBeVisible();

    await page.getByRole("table", { name: /Units for Avenue House/ }).getByRole("button", { name: "View" }).first().click();
    await expect(page).toHaveURL(new RegExp(`https?://[^/]+/studio/${AGENT_ID}/finance/property/A001\\?unit=101`));
    await expect(page.getByRole("heading", { name: "101" })).toBeVisible();
    await expect(page.getByRole("table", { name: /Unit expenses/ }).getByText("Electricity").first()).toBeVisible();
  });

  test("Expenditure and history pages render with filters", async ({ page }) => {
    await page.goto(`/studio/${AGENT_ID}/finance/expenditure?category=Utilities`);
    await dismissConsent(page);
    await expect(page.getByRole("heading", { name: /Expense category/ })).toBeVisible();
    await expect(page.getByText("2 expense rows")).toBeVisible();

    await page.goto(`/studio/${AGENT_ID}/finance/vendor/Acme%20Maintenance`);
    await dismissConsent(page);
    await expect(page.getByRole("heading", { name: "Acme Maintenance" })).toBeVisible();
    await expect(page.getByText("Vendor invoices").first()).toBeVisible();

    await page.goto(`/studio/${AGENT_ID}/finance/history`);
    await dismissConsent(page);
    await expect(page.getByText("No messages yet")).toBeVisible();
  });
});
