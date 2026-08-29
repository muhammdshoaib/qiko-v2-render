import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1014: uploading new workbooks left the dashboard's month filter on whatever month was
// previously selected. Since monthOptionsFromFiles derives its options from each file's
// *upload* timestamp (not the period the workbook covers), a stale or just-uploaded-today month
// selection can point at a month with zero rows, so the new data appears to vanish until the
// user manually reopens the date-range dropdown and picks "All time" themselves. Uploading should
// reset the filter to "All time" so newly uploaded data is visible immediately.
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
