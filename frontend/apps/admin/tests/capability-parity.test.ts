const capAssert = require("node:assert/strict");
const { existsSync: capExists, readFileSync: capRead } = require("node:fs");
const { resolve: capResolve } = require("node:path");
const capTest = require("node:test");

// The test runner compiles into .node-test-build/tests, so __dirname at runtime is not the source
// directory and a fixed number of ".." segments resolves differently under `pnpm test` than under a
// direct `node --test`. Walk up until the marker appears instead.
function capFind(relative: string): string {
  for (let up = 0; up < 8; up += 1) {
    const candidate = capResolve(__dirname, "../".repeat(up) || ".", relative);
    if (capExists(candidate)) return candidate;
  }
  throw new Error(`could not locate ${relative} from ${__dirname}`);
}

// The grant form renders checkboxes from ALL_CAPABILITIES and posts the selected set. A capability
// missing from that list is therefore not merely hidden: it cannot be granted at all, and saving an
// explicit set for an existing admin silently strips it. view_audit shipped to the backend without
// being added here, so for one release no operator could grant audit access, and editing a
// super_admin through this form removed theirs.
capTest("the console can grant every capability the backend enforces", () => {
  const backend = capRead(capFind("qiko-core/app/modules/identity/admin_rbac.py"), "utf8");
  // AdminRole is declared BEFORE Capability, so slicing between the two class names in source order
  // gave an empty string and the test passed on nothing. Anchored on what follows the enum instead.
  const start = backend.indexOf("class Capability");
  const enumBody = backend.slice(start, backend.indexOf("_DEFAULTS", start));
  const enforced = [...enumBody.matchAll(/^\s{4}(\w+)\s*=\s*"(\w+)"/gm)].map((m) => m[2]);
  capAssert.ok(enforced.length >= 9, `expected the backend enum, found ${enforced.length} entries`);

  const api = capRead(capFind("frontend/apps/admin/lib/api.ts"), "utf8");
  const listed = [...api.slice(api.indexOf("ALL_CAPABILITIES")).matchAll(/"(\w+)"/g)].map((m) => m[1]);
  const missing = enforced.filter((name) => !listed.includes(name));
  capAssert.deepEqual(missing, [],
    `ALL_CAPABILITIES is missing: ${missing.join(", ")}. Anything absent cannot be granted, and ` +
    "saving an explicit set for an existing admin strips it.");

  // And every one needs a human label, or the checkbox renders as undefined.
  const labels = capRead(capFind("frontend/apps/admin/app/admins/page.tsx"), "utf8");
  const labelled = labels.slice(labels.indexOf("const LABELS"), labels.indexOf("/** Removing an admin"));
  for (const name of enforced) {
    capAssert.match(labelled, new RegExp(`\\b${name}:`), `${name} has no label`);
  }
});
