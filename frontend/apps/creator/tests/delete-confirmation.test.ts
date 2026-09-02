const assert = require("node:assert/strict");
const { existsSync, readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const test = require("node:test");

const root = existsSync(resolve(__dirname, "../app"))
  ? resolve(__dirname, "..")
  : resolve(__dirname, "../..");
const read = (relative: string) => readFileSync(resolve(root, relative), "utf8");

const DELETE_FLOW_FILES = [
  "app/settings/page.tsx",
  "app/workers/[id]/page.tsx",
  "app/studio/[id]/sales-intelligence/pipeline/[oppId]/page.tsx",
  "app/studio/[id]/sales-intelligence/ingestion/page.tsx",
  "components/pre-sales/sources-tab.tsx",
  "components/pre-sales/section-assignment.tsx",
  "components/finance/file-manager.tsx",
];

for (const file of DELETE_FLOW_FILES) {
  test(`${file} uses ConfirmActionDialog instead of window.confirm for deletes`, () => {
    const source = read(file);
    const code = source.split("\n").filter((line: string) => !line.trim().startsWith("*") && !line.trim().startsWith("/*")).join("\n");
    assert.doesNotMatch(code, /window\.confirm/, `${file} must not use window.confirm for destructive actions`);
    assert.match(source, /useConfirmActionDialog|ConfirmActionDialog/, `${file} must use the shared confirmation dialog`);
  });
}

test("shared confirm dialog uses accessible AlertDialog primitive", () => {
  const source = read("components/confirm-action-dialog.tsx");
  assert.match(source, /AlertDialog/, "confirm dialog must render Radix AlertDialog");
  assert.match(source, /bg-\[#0a0f1a\]/, "confirm dialog must match V1 dark panel styling");
});
