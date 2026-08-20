import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1005: "Total Properties" (the KPI card) is the backend's raw property count
// (qiko-core/app/modules/finance/analytics.py: summary.propertyCount = len(real_refs), every
// property referenced in the period, not filtered by activity). The Profitability Classification
// donut instead classified only activeProperties(analytics) - properties with non-zero income,
// expenses, outstanding, or netProfit. A property with a zero-value row for the selected period
// (a reversed invoice, a placeholder entry, an otherwise-active property with no activity that
// month) is counted in Total Properties but silently dropped from the donut, so its slices never
// sum to the KPI's total. mapClassification already defaults safely for any property (unrecognized
// classes fall back to "profitable"), so there's no reason to exclude inactive ones here the way
// the vendor/risk/expense-category widgets legitimately do to avoid noise.
test("Profitability Classification donut counts every property, matching the Total Properties KPI", () => {
  const src = source("components/finance/utils.ts");
  const fn = src.slice(
    src.indexOf("export function classificationDonut"),
    src.indexOf("export function expenseCategoryDonut"),
  );

  assert.doesNotMatch(
    fn,
    /activeProperties\(/,
    "classificationDonut should classify analytics.properties directly, not the isActiveProperty-filtered subset",
  );
  assert.match(fn, /analytics\?\.properties\s*\?\?\s*\[\]/);
});
