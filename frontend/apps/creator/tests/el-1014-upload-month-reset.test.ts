import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1014 (part 1 of 2): uploading new workbooks left the dashboard's month filter on whatever
// month was previously selected, so a stale selection can point at a month with zero rows and the
// new data appears to vanish until the user manually reopens the dropdown and picks "All time"
// themselves. Uploading should reset the filter to "All time" so newly uploaded data is visible
// immediately. Part 2 (the month *options themselves* coming from the real transaction dates
// rather than each file's upload timestamp) is covered by monthOptionsFromAvailableMonths in
// finance-utils.test.ts.
test("finance file manager accepts an onUploaded callback fired after a successful upload", () => {
  const src = source("components/finance/file-manager.tsx");
  const uploadMutation = src.slice(src.indexOf("const upload = useMutation"), src.indexOf("const remove = useMutation"));
  assert.match(uploadMutation, /onSuccess:\s*\(\)\s*=>\s*\{[\s\S]*onUploaded\?\.\(\)/);
});

test("finance shell resets the month filter to all time when a workbook finishes uploading", () => {
  const src = source("components/finance/finance-shell.tsx");
  assert.match(src, /<FinanceFileManagerDialog[\s\S]*?onUploaded=\{\(\)\s*=>\s*setMonth\("all"\)\}/);
});

test("finance dashboard empty-state uploader also resets the month filter", () => {
  const src = source("app/studio/[id]/finance/page.tsx");
  assert.match(src, /<EmptyState[\s\S]*?onUploaded=\{\(\)\s*=>\s*setMonth\("all"\)\}/);
  assert.match(src, /<FinanceFileManager[\s\S]*?onUploaded=\{onUploaded\}/);
});
