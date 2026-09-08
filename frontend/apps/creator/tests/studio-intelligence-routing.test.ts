import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

test("StudioWorkerRouteGuard redirects bare /studio/:id to the worker's vertical cockpit", () => {
  const guardSource = readFileSync(
    resolve(process.cwd(), "components/studio/worker-route-guard.tsx"),
    "utf8",
  );
  // A bare /studio/:id URL is valid for the generic worker page, but verticals
  // (intelligence, finance, sales-intelligence, pre-sales) must redirect to
  // their cockpit. The guard should do this before the type-matching check.
  assert.match(guardSource, /pathname\s*===\s*`\s*\/studio\/\$\{id\}\s*`/);
  assert.match(guardSource, /router\.replace\s*\(\s*expectedPath(?:!)?\s*\)/);
});

test("StudioWorkerRouteGuard only blocks on a first load, not on every refetch (QIKO-1089)", () => {
  const guardSource = readFileSync(
    resolve(process.cwd(), "components/studio/worker-route-guard.tsx"),
    "utf8",
  );
  // isFetching is true for the background revalidation this query runs on every mount, so gating
  // the full-screen spinner on it blanked a cockpit that already had its data. Only isPending,
  // "no data yet", may block.
  assert.match(guardSource, /if\s*\(\s*access\.isPending\s*\)/);
  assert.doesNotMatch(guardSource, /access\.isFetching/);
});

test("StudioWorkerRouteGuard caches per worker, not per route (QIKO-1089)", () => {
  const guardSource = readFileSync(
    resolve(process.cwd(), "components/studio/worker-route-guard.tsx"),
    "utf8",
  );
  // The request is listAgents(), which does not vary by path. Keying on pathname gave every tab
  // inside a cockpit its own cache entry, making each in-cockpit navigation a cold fetch.
  assert.match(guardSource, /queryKey:\s*\["studio-worker-access",\s*id\]/);
  assert.doesNotMatch(guardSource, /queryKey:\s*\["studio-worker-access",\s*id,\s*pathname\]/);
});

test("Studio worker grid links intelligence workers to the intelligence cockpit", () => {
  const studioSource = readFileSync(
    resolve(process.cwd(), "app/studio/page.tsx"),
    "utf8",
  );
  assert.match(studioSource, /intelligence\s*=\s*a\.atype\s*===\s*"intelligence"/);
  assert.match(studioSource, /href\s*=\s*`\s*\/studio\/\$\{a\.id\}\/intelligence\s*`/);
});
