import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1010: "The finance worker chat should also work on the chat inside the main worker screen."
// The generic ChatTab always called the knowledge-base `ask()` endpoint, which has no access to
// the computed financial analytics a finance worker answers from -- so finance questions asked
// from /workers/{id} never worked the way they do from the Studio finance cockpit.
test("worker screen chat routes finance workers through the finance chat, not the generic knowledge chat", () => {
  const src = source("app/workers/[id]/page.tsx");
  const chatTab = src.slice(src.indexOf("function ChatTab"));

  assert.match(src, /\bfinanceChat\b/);
  assert.match(src, /\bgetFinanceHistory\b/);
  assert.match(chatTab, /worker\?\.atype === "finance"/);
  assert.match(chatTab, /financeChat\(id, q\)/);
  // The finance chat is the same persisted conversation as the Studio cockpit: seed the
  // transcript from it instead of always starting blank.
  assert.match(chatTab, /getFinanceHistory\(id\)/);
});
