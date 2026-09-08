import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1022: "the full page refreshes whenever the user changes tabs." History used to be its own
// route (router.push(historyHref)), so switching to it from Intelligence or Chat was a genuine
// cross-route navigation: it unmounted whatever page you left, mounted a fresh History page, and
// refetched its data every single time -- even though EL-1011 had already removed *redundant*
// pushes for a tab you were already on, that never addressed the cost of a real, different-route
// tab switch. History is now an in-page panel kept mounted alongside Chat and the dashboard
// (children), toggled with the same CSS-hide pattern EL-1016/EL-1019 already established for
// Chat, so switching tabs is a pure state change with no navigation and no remount.
test("finance shell keeps the history panel mounted alongside chat and the dashboard, toggling visibility with CSS", () => {
  const src = source("components/finance/finance-shell.tsx");
  assert.match(src, /import\s*\{\s*FinanceHistoryPanel\s*\}\s*from\s*["']@\/components\/finance\/history-panel["']/);
  assert.match(src, /<FinanceHistoryPanel agentId=\{agentId\}\s*\/>/);
  // History's wrapper is hidden (not unmounted) when tab isn't "history".
  const panelIndex = src.indexOf("<FinanceHistoryPanel agentId");
  const historyWrapper = src.slice(src.lastIndexOf("<div", panelIndex), panelIndex);
  assert.match(historyWrapper, /tab === "history" \? "flex" : "hidden"/);
  // The dashboard/children side is hidden when tab is either "chat" or "history", not unmounted.
  assert.match(src, /tab !== "feed" && "hidden"/);
});

test("switching to or from the history tab never calls router.push", () => {
  const src = source("components/finance/finance-shell.tsx");
  const goHistoryStart = src.indexOf("function goHistory");
  const goHistory = src.slice(goHistoryStart, src.indexOf("\n  }", goHistoryStart));
  assert.doesNotMatch(goHistory, /router\.push/);
  assert.match(goHistory, /setChatTab\(false\)/);
  assert.match(goHistory, /setHistoryTab\(true\)/);
});

// A direct link/bookmark to /finance/history must still land on the history panel active,
// even though the tab bar no longer navigates there itself. This must seed the *real*
// historyTab state (via an effect), not a separate frozen "landed here" flag -- a frozen flag
// can never clear, which would pin the tab to "history" forever even after later clicking
// Intelligence or Chat away from it.
test("landing directly on the history route seeds the real historyTab state, not a separate frozen flag", () => {
  const src = source("components/finance/finance-shell.tsx");
  const effect = src.slice(src.indexOf("useEffect(() => {\n    if (pathname === historyHref)"), src.indexOf("}, []);") + 7);
  assert.match(effect, /setHistoryTab\(true\)/);
  assert.match(src, /const tab = chatTab \? "chat" : historyTab \? "history" : "feed"/);
});
