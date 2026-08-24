import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1011: switching between Intelligence, Chat and History tabs in the finance cockpit must not
// trigger a full page reload. The feed and history tabs are route-backed, but clicking the active
// tab (or returning from the in-page Chat tab) should only toggle state, not re-push the route.
test("finance tab switches avoid redundant router.push calls", () => {
  const src = source("components/finance/finance-shell.tsx");
  const goFeed = src.slice(src.indexOf("function goFeed"), src.indexOf("function goChat"));
  const goHistoryStart = src.indexOf("function goHistory");
  const goHistory = src.slice(goHistoryStart, src.indexOf("\n  return (", goHistoryStart));

  assert.match(goFeed, /if \(!isDashboard\) router\.push\(dashboardHref\)/);
  assert.equal((goFeed.match(/router\.push\(/g) || []).length, 1);
  assert.match(goHistory, /if \(!isHistory\) router\.push\(historyHref\)/);
  assert.equal((goHistory.match(/router\.push\(/g) || []).length, 1);
});
