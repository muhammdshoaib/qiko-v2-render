import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1016/EL-1019: switching away from the Chat tab (and back) fully unmounted FinanceChatPanel
// via a `tab === "chat" ? X : Y` ternary, wiping its in-memory `messages` state ("the chat window
// clears all the data") and, symmetrically, unmounting the dashboard side every time you opened
// Chat ("the page refreshes"). Both sides must stay mounted and only be hidden with CSS.
test("finance shell keeps both the chat panel and the dashboard side mounted, toggling visibility with CSS", () => {
  const src = source("components/finance/finance-shell.tsx");
  // No more full-branch ternary excluding one side from the tree.
  assert.doesNotMatch(src, /\{tab === "chat" \? \(/);
  assert.match(src, /<FinanceChatPanel/);
  // FinanceChatPanel's wrapper is hidden (not unmounted) when tab isn't "chat".
  const chatWrapper = src.slice(src.indexOf('<div className={cn("min-h-0 w-full min-w-0 flex-1'), src.indexOf("<FinanceChatPanel"));
  assert.match(chatWrapper, /tab === "chat" \? "flex" : "hidden"/);
  // The dashboard/children side is hidden (not unmounted) when tab is "chat" (or, since EL-1022,
  // "history" -- both are now in-page panels, so children is hidden whenever tab isn't "feed").
  assert.match(src, /tab !== "feed" && "hidden"/);
});

// EL-1019: even on a genuine remount (first load, full page refresh), the chat should rehydrate
// from the persisted conversation instead of always starting blank.
test("finance chat panel rehydrates its transcript from finance history on mount", () => {
  const src = source("components/finance/chat-panel.tsx");
  assert.match(src, /import\s*\{[^}]*\bgetFinanceHistory\b[^}]*\}\s*from\s*["']@\/lib\/api["']/);
  assert.match(src, /getFinanceHistory\(agentId\)/);
  assert.match(src, /res\.history\.map\(\(h\)\s*=>\s*\(\{\s*role:\s*h\.role,\s*text:\s*h\.content\s*\}\)\)/);
});

// The history-rehydration fetch and the pendingPrompt auto-submit effect both fire on mount
// (InsightRail sets pendingPrompt and is visible on first load), so the fetch resolving after an
// optimistic user message was appended must not wipe it from view.
test("finance chat panel history rehydration does not clobber an in-flight message", () => {
  const src = source("components/finance/chat-panel.tsx");
  const historyEffect = src.slice(src.indexOf("getFinanceHistory(agentId)"), src.indexOf("useEffect", src.indexOf("getFinanceHistory(agentId)")));
  assert.match(historyEffect, /setMessages\(\(current\)\s*=>\s*\(current\.length > 0 \? current : /);
});

// EL-1016/EL-1019: the History tab now stays mounted while chatting, so a new exchange must
// invalidate its query instead of leaving a stale transcript until a manual refresh.
test("sending a finance chat message invalidates the finance-history query", () => {
  const src = source("components/finance/chat-panel.tsx");
  assert.match(src, /import\s*\{[^}]*\buseQueryClient\b[^}]*\}\s*from\s*["']@tanstack\/react-query["']/);
  assert.match(src, /invalidateQueries\(\{\s*queryKey:\s*\["finance-history",\s*agentId\]\s*\}\)/);
});
