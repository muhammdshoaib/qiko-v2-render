import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1011: switching between Intelligence, Chat and History tabs in the finance cockpit must not
// trigger a full page reload. The feed tab is route-backed (it can be reached from a drilled-down
// page like /finance/property/:ref, so it genuinely needs to navigate back), but clicking the
// active tab should not re-push the route it's already on.
//
// EL-1022: History used to be route-backed the same way (router.push(historyHref)), which meant
// switching to it was always a genuine cross-route navigation -- unmounting/remounting whatever
// page you left and refetching History's own data every time. That's a bigger version of the
// same "feels like a refresh" complaint EL-1011 fixed for redundant same-route pushes, so History
// moved to an in-page panel toggled by state instead (see el-1022-history-panel-persists.test.ts),
// exactly like Chat. It no longer navigates at all when switching to or from it.
test("the feed tab avoids a redundant router.push call, history tab never navigates", () => {
  const src = source("components/finance/finance-shell.tsx");
  const goFeed = src.slice(src.indexOf("function goFeed"), src.indexOf("function goChat"));
  const goHistoryStart = src.indexOf("function goHistory");
  const goHistory = src.slice(goHistoryStart, src.indexOf("\n  return (", goHistoryStart));

  assert.match(goFeed, /if \(!isDashboard\) router\.push\(dashboardHref\)/);
  assert.equal((goFeed.match(/router\.push\(/g) || []).length, 1);
  assert.doesNotMatch(goHistory, /router\.push/);
  assert.match(goHistory, /setHistoryTab\(true\)/);
});
