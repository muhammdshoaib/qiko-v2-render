import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1017: deleting a finance workbook or an intelligence document fired the delete mutation
// straight from the trash-icon button's onClick, with no confirmation step at all. Both should
// show a confirm dialog first. Originally fixed with a local @qiko/ui Dialog + pendingDelete
// state (matching the pattern then used for deleting a worker behavior entry); QIKO-1063 replaced
// that local pattern across the app with the shared useConfirmActionDialog, so the finance file
// manager's own confirmation now goes through that instead - same guarantee, one implementation.
test("finance file manager confirms before deleting a workbook", () => {
  const src = source("components/finance/file-manager.tsx");
  assert.match(src, /import\s*\{\s*useConfirmActionDialog\s*\}\s*from\s*["']@\/components\/confirm-action-dialog["']/);
  // The trash button no longer deletes directly on click.
  assert.doesNotMatch(src, /onClick=\{\(\)\s*=>\s*remove\.mutate\(f\.id\)\}/);
  assert.match(src, /openConfirmationDialog\(/);
  assert.match(src, /isDestructive:\s*true/);
});

test("documents tab confirms before deleting a document", () => {
  const src = source("components/documents-tab.tsx");
  assert.match(src, /import\s*\{[^}]*\bDialog\b[^}]*\}\s*from\s*["']@qiko\/ui["']/);
  assert.match(src, /pendingDelete/);
  assert.doesNotMatch(src, /onDelete=\{\(\)\s*=>\s*remove\.mutate\(doc\.doc_id\)\}/);
});

// The finance file manager's confirm dialog is nested inside another (Radix) dialog. Radix's own
// Escape handling is a document-level *capture*-phase listener, which runs before any bubble-phase
// handler on the nested confirmation could ever call stopPropagation() -- so the only thing that
// can actually stop it is the outer Radix dialog's own `onEscapeKeyDown` prop, guarded on whether
// the confirmation is currently open.
test("the finance file manager dialog blocks Escape while its delete confirmation is open", () => {
  const src = source("components/finance/file-manager.tsx");
  assert.match(src, /onConfirmOpenChange/);
  const dialogFn = src.slice(src.indexOf("export function FinanceFileManagerDialog"));
  assert.match(dialogFn, /onEscapeKeyDown=\{\(e\)\s*=>\s*\{\s*if\s*\(confirmOpen\)\s*e\.preventDefault\(\);?\s*\}\}/);
});
