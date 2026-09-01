import assert from "node:assert/strict";
import test from "node:test";

import {
  formatCurrency,
  formatCompact,
  normalizeFinanceSummary,
  kpiMetricDrilldown,
  propertyBars,
  vendorRows,
  expenseCategoryDonut,
  monthOptionsFromAvailableMonths,
  type KpiMetricKey,
} from "../components/finance/utils";

function expectedCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

test("formatCurrency formats with explicit currency", () => {
  assert.equal(formatCurrency(1234.5, "USD"), expectedCurrency(1234.5, "USD"));
});

test("formatCurrency falls back to GBP only when currency is omitted", () => {
  assert.ok(formatCurrency(1234.5).startsWith("£"));
});

test("formatCurrency renders null and undefined as -", () => {
  assert.equal(formatCurrency(null, "GBP"), "-");
  assert.equal(formatCurrency(undefined, "GBP"), "-");
});

test("formatCompact renders zero as currency", () => {
  assert.ok(formatCompact(0, "EUR").includes("€"));
});

test("normalizeFinanceSummary returns flat numeric summary without stale formatted/subtitle/details maps", () => {
  const summary = normalizeFinanceSummary({
    totalIncome: 1000,
    totalExpenses: 200,
    netProfit: 800,
    propertyCount: 2,
    vendorCount: 1,
    outstanding: 0,
  } as any);
  assert.equal(summary.totalIncome, 1000);
  assert.equal(summary.totalExpenses, 200);
  assert.equal(summary.netProfit, 800);
  assert.equal(summary.propertyCount, 2);
  assert.equal(summary.vendorCount, 1);
  assert.equal(summary.outstanding, 0);
  assert.equal("formatted" in summary, false);
  assert.equal("subtitle" in summary, false);
  assert.equal("details" in summary, false);
});

test("kpiMetricDrilldown formats total and numeric detail fields with currency", () => {
  const summary = {
    totalIncome: 1000,
    totalIncomeUnitCount: 5,
    totalIncomeAveragePerProperty: 200,
    totalIncomeTopProperty: "Alpha",
    totalIncomeTopPropertyRef: "A-1",
    totalIncomeTopPropertyIncome: 900,
  } as any;
  const result = kpiMetricDrilldown(summary, "totalIncome" as KpiMetricKey, "USD");
  assert.equal(result.title, "Total Income");
  assert.equal(result.formatted, expectedCurrency(1000, "USD"));
  assert.ok(result.details.some(([label, value]) => label === "Total Income Unit Count" && value === "5"));
  assert.ok(result.details.some(([label, value]) => label === "Total Income Average Per Property" && value === expectedCurrency(200, "USD")));
  assert.ok(result.details.some(([label, value]) => label === "Total Income Top Property" && value === "Alpha"));
  assert.ok(result.details.some(([label, value]) => label === "Total Income Top Property Income" && value === expectedCurrency(900, "USD")));
});

test("kpiMetricDrilldown expands expenseBreakdown and formats monetary sub-fields", () => {
  const summary = {
    totalExpenses: 330,
    expenseBreakdown: { net: 300, vat: 30 },
    totalExpensesInvoiceCount: 10,
  } as any;
  const result = kpiMetricDrilldown(summary, "totalExpenses" as KpiMetricKey, "EUR");
  assert.equal(result.formatted, expectedCurrency(330, "EUR"));
  assert.ok(result.details.some(([label, value]) => label.includes("Net") && value === expectedCurrency(300, "EUR")));
  assert.ok(result.details.some(([label, value]) => label.includes("Vat") && value === expectedCurrency(30, "EUR")));
  assert.ok(result.details.some(([label, value]) => label === "Total Expenses Invoice Count" && value === "10"));
});

test("propertyBars preserves decimals from analytics", () => {
  const analytics = {
    properties: [{
      name: "Alpha",
      propertyRef: "A-1",
      income: 180842.30,
      expenses: 2777.50,
      netProfit: 178064.80,
      marginPercent: 1.5,
      outstanding: 0,
    }],
  } as any;
  const bars = propertyBars(analytics);
  assert.equal(bars[0].income, 180842.30);
  assert.equal(bars[0].expenses, 2777.50);
  assert.equal(bars[0].profit, 178064.80);
});

test("vendorRows and expenseCategoryDonut preserve decimals", () => {
  const analytics = {
    summary: { totalExpenses: 2777.50 },
    properties: [{
      propertyRef: "A-1",
      income: 0,
      expenses: 2777.50,
      netProfit: 0,
      expenseCategories: [{ category: "Repairs", amount: 1234.56 }],
      topVendors: [{ vendorName: "ACME", amount: 1234.56 }],
    }],
  } as any;

  const vendors = vendorRows(analytics);
  assert.equal(vendors[0].spend, 1234.56);
  assert.ok(vendors[0].percent > 0);

  const categories = expenseCategoryDonut(analytics);
  assert.equal(categories[0].value, 1234.56);
});

test("kpiMetricDrilldown shows missing values as -", () => {
  const summary = {
    totalIncome: 0,
    totalIncomeTopProperty: "",
    totalIncomeTopPropertyIncome: null,
  } as any;
  const result = kpiMetricDrilldown(summary, "totalIncome" as KpiMetricKey, "GBP");
  assert.ok(result.details.some(([label, value]) => label === "Total Income Top Property" && value === "-"));
  assert.ok(result.details.some(([label, value]) => label === "Total Income Top Property Income" && value === "-"));
});

// EL-1014: the dropdown used to be built from each uploaded file's *upload* timestamp, so two
// files uploaded together on the same day collapsed to one (wrong) month option no matter which
// real periods their data covered. Options must come straight from the backend's availableMonths
// (derived from the real transaction dates), not from any client-side file metadata.
test("monthOptionsFromAvailableMonths builds one option per distinct backend month, oldest first, plus All time", () => {
  const opts = monthOptionsFromAvailableMonths(["2026-02", "2025-12"]);
  assert.deepEqual(opts, [
    { label: "All time", value: "all" },
    { label: "Dec 2025", value: "2025-12" },
    { label: "Feb 2026", value: "2026-02" },
  ]);
});

test("monthOptionsFromAvailableMonths de-dupes a repeated month", () => {
  // Defence-in-depth: the backend already de-dupes via a Python set, but the dropdown must not
  // show the same month twice even if that ever changed.
  const opts = monthOptionsFromAvailableMonths(["2025-12", "2025-12"]);
  const values = opts.map((o) => o.value).filter((v) => v !== "all");
  assert.deepEqual(values, ["2025-12"]);
});

test("monthOptionsFromAvailableMonths tolerates missing/empty input", () => {
  assert.deepEqual(monthOptionsFromAvailableMonths(undefined), [{ label: "All time", value: "all" }]);
  assert.deepEqual(monthOptionsFromAvailableMonths([]), [{ label: "All time", value: "all" }]);
});
