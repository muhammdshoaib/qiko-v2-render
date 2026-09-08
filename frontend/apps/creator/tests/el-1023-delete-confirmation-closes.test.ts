import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1023: every caller of useConfirmActionDialog follows the same pattern -- setPending(true),
// then mutate() with onSuccess calling closeConfirmationDialog() and onSettled calling
// setPending(false). React Query always runs onSuccess before onSettled, so closeConfirmationDialog
// was called while `pending` was still true. closeConfirmationDialog used to refuse to close while
// pending ("if (prev.pending) return prev"), a guard meant to stop a *user* dismissing the dialog
// (Escape/backdrop click) mid-action -- but it also silently swallowed the caller's own "we're
// done, close now" call, leaving the dialog open with the action already completed (file deleted,
// modal still showing "Delete workbook?"). This affects every one of this hook's ~8 call sites
// across the app (file manager, document deletion, API key revoke, behavior entries, settings),
// not just finance, since they all share this one hook.
test("closeConfirmationDialog always closes, regardless of the pending flag", () => {
  const src = source("components/confirm-action-dialog.tsx");
  const closeFn = src.slice(
    src.indexOf("const closeConfirmationDialog"),
    src.indexOf("const setPending"),
  );
  assert.doesNotMatch(closeFn, /if\s*\(prev\.pending\)\s*return\s*prev/,
    "closeConfirmationDialog must not refuse to close while pending -- every caller relies on " +
    "calling it directly from a mutation's onSuccess, which always runs before onSettled resets " +
    "pending back to false");
  assert.match(closeFn, /setDialog\(CLOSED\)/);
});

// The pending guard still has to live *somewhere*, so a user can't Escape/backdrop-click out of
// the dialog while a delete is actually in flight (the Cancel button already disables itself the
// same way). It belongs in onOpenChange, which is only invoked for a user-initiated dismiss
// attempt, not in closeConfirmationDialog which callers also invoke directly after success.
test("a user-initiated dismiss (onOpenChange) is still blocked while pending", () => {
  const src = source("components/confirm-action-dialog.tsx");
  const onOpenChange = src.slice(src.indexOf("onOpenChange={(open"), src.indexOf(">\n      <AlertDialogContent"));
  assert.match(onOpenChange, /if\s*\(!open\s*&&\s*!dialog\.pending\)\s*closeConfirmationDialog\(\)/);
});
