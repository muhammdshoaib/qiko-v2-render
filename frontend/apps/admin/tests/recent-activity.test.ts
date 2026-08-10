const raAssert = require("node:assert/strict");
const { existsSync: raExists, readFileSync: raRead } = require("node:fs");
const { resolve: raResolve } = require("node:path");
const raTest = require("node:test");

function raFind(relative: string): string {
  for (let up = 0; up < 8; up += 1) {
    const candidate = raResolve(__dirname, "../".repeat(up) || ".", relative);
    if (raExists(candidate)) return candidate;
  }
  throw new Error(`could not locate ${relative} from ${__dirname}`);
}
const raAdmin = "frontend/apps/admin/";
const panel = raRead(raFind(`${raAdmin}components/recent-activity.tsx`), "utf8");
const drawer = raRead(raFind(`${raAdmin}components/row-activity-dialog.tsx`), "utf8");
const customerDialog = raRead(raFind(`${raAdmin}components/customer-detail-dialog.tsx`), "utf8");
const backend = raRead(raFind("qiko-core/app/modules/admin/router.py"), "utf8");

raTest("being refused is a normal state, not an error", () => {
  // Most admins reading a customer record do not hold view_audit. A 403 here must not take down the
  // dialog it sits inside, and a red error box inside a customer record reads as something broken.
  raAssert.match(panel, /retry: false/);
  raAssert.match(panel, /needs the Read the audit log capability/);
  raAssert.doesNotMatch(panel, /tone="error"/, "a refusal is not an error");
});

raTest("the window is wide, because a quiet account is the point", () => {
  // On a rarely-touched account the last thing that happened is the interesting thing, however long
  // ago. An empty panel because the window was seven days is indistinguishable from an empty panel
  // because nothing happened.
  raAssert.match(panel, /days: 400/);
  // And 400 is the server's own ceiling, so the client cannot ask for more than the endpoint allows.
  raAssert.match(backend, /days: int = Query\(default=7, ge=1, le=400\)/);
});

raTest("the panel names the coverage gap it has", () => {
  // Worker availability changes still live in the older agent_state_audit table and are not in this
  // stream. A reader seeing an empty panel must not conclude nothing happened.
  raAssert.match(panel, /note\?: string/);
  raAssert.match(customerDialog, /note="Worker availability changes are listed separately below\."/);
  // Shown even when the list is populated: the gap does not disappear because something else was
  // recorded.
  raAssert.match(panel, /\{note && activity\.isSuccess &&/);
});

raTest("the legacy section is labelled for what it actually contains", () => {
  // It was called "Worker audit history", which implied completeness it never had now that a unified
  // trail exists alongside it.
  raAssert.match(customerDialog, /Worker availability history/);
  raAssert.doesNotMatch(customerDialog, /Worker audit history/);
});

raTest("the panel leads to the full trail with its filter applied", () => {
  // Five entries answer "is anything odd here". The link answers everything else, and typing a filter
  // by hand is the step operators skip.
  raAssert.match(panel, /\/audit\?tenant=\$\{encodeURIComponent/);
  raAssert.match(panel, /\/audit\?target=\$\{encodeURIComponent/);
  raAssert.match(panel, /Open in audit log/);
});

raTest("the scope is one of tenant or target, not both", () => {
  // A row-level question is about that row; an account-level question is about the account. Allowing
  // both would silently pick one.
  raAssert.match(panel, /\| \{ tenantId: string; targetId\?: never \}/);
  raAssert.match(panel, /\| \{ targetId: string; tenantId\?: never \}/);
});

raTest("the three read-only directories can now reach a row's history", () => {
  // They had no detail view at all, so an operator who noticed something odd about a row had nowhere to
  // go but the global page and a hand-typed filter.
  for (const name of ["tenants", "users", "workers"]) {
    const page = raRead(raFind(`${raAdmin}app/${name}/page.tsx`), "utf8");
    raAssert.match(page, /RowActivityDialog/, `${name} needs a way into the history`);
    raAssert.match(page, /aria-label=\{`Recent activity for/, `${name} action needs an accessible name`);
  }
});

raTest("users and workers narrow by row, tenants by account", () => {
  const users = raRead(raFind(`${raAdmin}app/users/page.tsx`), "utf8");
  const workers = raRead(raFind(`${raAdmin}app/workers/page.tsx`), "utf8");
  const tenants = raRead(raFind(`${raAdmin}app/tenants/page.tsx`), "utf8");
  raAssert.match(users, /targetId=\{active\?\.id\}/, "a user row asks about that person");
  raAssert.match(workers, /targetId=\{active\?\.id\}/);
  raAssert.match(tenants, /tenantId=\{active\?\.tenant_id\}/, "a tenant row asks about the account");
});

raTest("the drawer restores focus to whatever opened it", () => {
  raAssert.match(drawer, /opener\.current = document\.activeElement/);
  raAssert.match(drawer, /opener=\{opener\.current\}/);
  raAssert.match(drawer, /labelledBy="row-activity-title"/);
});

raTest("the drawer mounts the panel only while open", () => {
  // Otherwise every row in the directory fires a query for history nobody asked to see.
  raAssert.match(drawer, /\{open && \(\s*<RecentActivity/);
});

raTest("the sentence comes from the server, here too", () => {
  // Same reason as the global page: rebuilding it from current labels would change history
  // retroactively on a rename.
  raAssert.match(panel, /headline\(event\)/);
  raAssert.doesNotMatch(panel, /event\.action \+/, "no client-side sentence assembly");
});
