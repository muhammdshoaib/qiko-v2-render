import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import { APP_SHELL_ROUTE_PREFIXES, isAppShellRoute } from "../lib/consent/app-shell-routes";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1000 / EL-1009: the KPI cards on the Financial Analyst dashboard match V1's 4-card layout
// (Income, Expenses, Net Profit, Total Properties - no separate Outstanding card) and show only
// a label and a value, no drill-in detail lines (those belong to the drilldown pages).
test("KPI cards render V1's four headline metrics with no detail breakdown lines", () => {
  const src = source("components/finance/kpi-cards.tsx");

  assert.match(src, /label="Total Income"/);
  assert.match(src, /label="Total Expenses"/);
  assert.match(src, /label="Net Profit"/);
  assert.match(src, /label="Total Properties"/);
  assert.doesNotMatch(src, /label="Outstanding"/);

  for (const removed of [
    "totalIncomeTopProperty", "totalIncomeAveragePerProperty", "totalIncomeUnitCount",
    "totalExpensesTopVendor", "totalExpensesTopCategory", "totalExpensesInvoiceCount", "totalExpensesAveragePerProperty",
    "netProfitMarginPercent", "netProfitAverageMargin", "netProfitTopProperty", "netProfitLowestPerformanceProperty", "netProfitCostToIncomeRatio",
    "outstandingPropertyCount", "outstandingPositiveTotal", "outstandingNegativeTotal", "outstandingTopProperty", "outstandingAsPercentOfIncome",
    "highPerforming", "averagePerforming", "underPerforming", "highRisk", "mediumRisk", "lowRisk",
    "totalUnits", "totalInvoices", "averageIncomePerProperty", "averageExpensePerProperty", "topProperty", "worstProperty",
  ]) {
    assert.doesNotMatch(src, new RegExp(removed), `kpi-cards.tsx should no longer reference ${removed}`);
  }
});

// EL-1001: the global floating cookie-settings button must not render on AppShell'd routes,
// where it has twice collided with in-app chrome (Logout, then the chat send button).
test("AppShell route predicate matches every authenticated app route and no public route", () => {
  assert.deepEqual([...APP_SHELL_ROUTE_PREFIXES].sort(), ["/billing", "/chat", "/dashboard", "/settings", "/studio", "/workers"]);

  for (const appRoute of [
    "/dashboard", "/workers", "/workers/abc123", "/studio", "/studio/el-finance-001",
    "/studio/el-finance-001/finance", "/studio/el-finance-001/finance/property/A001",
    "/settings", "/chat/abc123", "/billing",
  ]) {
    assert.equal(isAppShellRoute(appRoute), true, `${appRoute} should be treated as an AppShell route`);
  }

  for (const publicRoute of ["/", "/login", "/signup", "/cookies", "/privacy", "/terms", "/forgot-password", "/reset-password", "/verify-email"]) {
    assert.equal(isAppShellRoute(publicRoute), false, `${publicRoute} should not be treated as an AppShell route`);
  }
});

test("floating consent settings button is gated on AppShell routes", () => {
  const src = source("components/consent/ConsentUI.tsx");
  const floatingBranch = src.slice(src.indexOf('if (variant === "floating")'));

  assert.match(src, /from "next\/navigation"/);
  assert.match(floatingBranch, /isAppShellRoute\(pathname\)\)\s*return null;/);
});

// EL-1004: the per-row "View unit" action in a unit-scoped expense list is a no-op (it navigates
// to the exact page already being viewed), so property-detail.tsx's "Unit expenses" list must
// suppress it.
test("unit-scoped expense list suppresses the redundant View unit action", () => {
  const expenseListSrc = source("components/finance/expense-list.tsx");
  const propertyDetailSrc = source("components/finance/property-detail.tsx");

  assert.match(expenseListSrc, /hideViewUnitAction/);
  assert.match(expenseListSrc, /actions=\{hideViewUnitAction \? undefined :/);

  const unitExpensesCall = propertyDetailSrc.slice(
    propertyDetailSrc.lastIndexOf("<ExpenseList", propertyDetailSrc.indexOf('title="Unit expenses"')),
    propertyDetailSrc.indexOf("/>", propertyDetailSrc.indexOf('title="Unit expenses"')),
  );
  assert.match(
    unitExpensesCall,
    /hideViewUnitAction/,
    "the Unit expenses ExpenseList (already scoped to one unit) should pass hideViewUnitAction",
  );
});

// EL-1006: Property Profitability Ranking colors bars per-point via <Cell>, so its Tooltip has no
// series-level fill for Recharts to key its default (black) item text color off. Force a readable
// color explicitly.
test("Property Profitability Ranking tooltip forces readable (non-default) item text color", () => {
  const src = source("components/finance/charts.tsx");
  const rankingChart = src.slice(src.indexOf("export function ProfitabilityRankingChart"));
  assert.match(rankingChart, /<Tooltip[^>]*itemStyle=/);
});
