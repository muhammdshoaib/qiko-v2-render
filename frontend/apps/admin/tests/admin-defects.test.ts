const defectsAssert = require("node:assert/strict");
const { existsSync: defectsExistsSync, readFileSync: defectsReadFileSync } = require("node:fs");
const { resolve: defectsResolve } = require("node:path");
const defectsTest = require("node:test");

// Source-level regression guards for a batch of defects found by auditing the admin console. Each
// one shipped to production and none was caught by a test, so each gets a pin here.
const defectsRoot = defectsExistsSync(defectsResolve(__dirname, "../app"))
  ? defectsResolve(__dirname, "..")
  : defectsResolve(__dirname, "../..");
const read = (relative: string) => defectsReadFileSync(defectsResolve(defectsRoot, relative), "utf8");

defectsTest("every nav destination declares the capability its backend enforces", () => {
  // Four entries declared none while their endpoints required one, so a narrowed admin saw the item,
  // clicked it, and got an error card. A menu offering what it cannot deliver is worse than a short one.
  const shell = read("components/app-shell.tsx");
  const navBlock = shell.slice(shell.indexOf("const NAV"), shell.indexOf("];", shell.indexOf("const NAV")));
  // Only the entry lines, not the type declaration that also mentions href.
  for (const line of navBlock.split("\n").filter((l: string) => l.trim().startsWith("{ href:"))) {
    // /security is the deliberate exception: it is the 2FA enrolment escape hatch every admin needs.
    if (line.includes('"/security"')) continue;
    defectsAssert.match(line, /requires: "/, `nav entry without a capability: ${line.trim()}`);
  }
});

defectsTest("admin actions gate on capabilities, never on the coarse role", () => {
  // The server enforces manage_customers / manage_workers / manage_billing. Comparing to
  // "super_admin" hid actions from admins explicitly granted them and would have offered them to a
  // narrowed super_admin who was not.
  for (const file of ["app/invoices/page.tsx", "components/customer-detail-dialog.tsx"]) {
    const source = read(file);
    defectsAssert.doesNotMatch(source, /role === "super_admin"/,
      `${file} must gate on a capability, not the role`);
    defectsAssert.doesNotMatch(source, /role === "viewer"/,
      `${file} must gate on a capability, not the role`);
    defectsAssert.match(source, /capabilities\?\.includes\(/, `${file} must check a capability`);
  }
});

defectsTest("every paginated list actually paginates", () => {
  // /monitoring and /subscriptions both called paginated endpoints without ever sending a page, so
  // everything past the twentieth row was unreachable while the heading reported the true total.
  //
  // The property that matters is that the page reaches the FETCHER. A first version of this test only
  // checked that setPage and a page indicator existed, and it stayed green when the page was removed
  // from the query, which is exactly the bug. It also has to be in the query key, or React Query
  // serves the cached first page forever.
  // Leg D moved the page into the URL and the four cross-tenant directories onto one shared shell, so
  // the fetcher and the page control live there rather than per page. The property is unchanged: the
  // page must reach the fetcher AND be in the query key, or React Query serves page one forever.
  // All six lists now delegate the query to the shared shell, so the property is asserted once there
  // and each page only has to pass the page through its fetcher. This assertion has been rewritten
  // twice as the lists moved; what has never changed is what it checks, which is that the page reaches
  // the API and is part of the cache key.
  const shell = read("components/directory-page.tsx");
  defectsAssert.match(shell, /queryKey: \[[^\]]*page[^\]]*\]/, "the shell must key the query on the page");
  defectsAssert.match(shell, /fetchPage\(urlSearch, page, sort\)/);
  defectsAssert.match(read("app/monitoring/page.tsx"), /workerMonitoring\(\n?\s*days, page,/);
  defectsAssert.match(read("app/subscriptions/page.tsx"), /listCustomers\(search, page, sort/);
  defectsAssert.match(shell, /<Pagination /, "the shell must render a page control");
  defectsAssert.match(shell, /params\.get\("page"\)/, "the page must be shareable in a link");
  // No page keeps its own page state any more. A stray setPage would mean a list drifted back off the
  // shell, which is how five near-identical implementations happened the first time.
  for (const file of ["app/subscriptions/page.tsx", "app/monitoring/page.tsx",
                      "app/customers/page.tsx", "app/tenants/page.tsx", "app/users/page.tsx",
                      "app/workers/page.tsx"]) {
    defectsAssert.doesNotMatch(read(file), /setPage\(/, `${file} must not own page state`);
  }
});

defectsTest("list result counts describe the view, not just a total", () => {
  // "137 total" is identical before and after a filter that returns 137 of a different set, so the
  // live region announced nothing. A range plus a total is change-detectable.
  // Announced once, in the shell every list uses.
  defectsAssert.match(read("components/directory-page.tsx"), /Showing \$\{firstOnPage\}/);
});

defectsTest("lists keep their rows while the next page loads", () => {
  // Without this the query key change collapsed the whole list into skeleton bars on every click.
  defectsAssert.match(read("components/directory-page.tsx"), /placeholderData: keepPreviousData/);
});

defectsTest("money is formatted once, in the currency Stripe is actually charged in", () => {
  // Tenants rendered earnings_cents as GBP while customers hardcoded "$" for the same figure.
  // integrations/clients.py sends currency "usd", so USD is the true one.
  defectsAssert.match(read("lib/api.ts"), /currency: "USD"/);
  for (const file of ["app/tenants/page.tsx", "app/customers/page.tsx", "app/invoices/page.tsx",
                      "app/subscriptions/page.tsx"]) {
    const source = read(file);
    defectsAssert.doesNotMatch(source, /currency: "GBP"/, `${file} must not invent a currency`);
    defectsAssert.doesNotMatch(source, /\$\{\(.*earnings_cents \/ 100\)/, `${file} must use formatMoney`);
  }
});

defectsTest("an empty list distinguishes no data from no matches", () => {
  // "No workers match this filter" was shown even when the platform had zero workers, and the reverse.
  defectsAssert.match(read("components/directory-page.tsx"), /emptyMessage: \(filtered: boolean\)/);
  for (const file of ["app/tenants/page.tsx", "app/users/page.tsx", "app/workers/page.tsx"]) {
    defectsAssert.match(read(file), /emptyMessage=\{\(filtered\) =>/, `${file} must vary its empty text`);
  }
});

defectsTest("errors are announced to assistive technology", () => {
  // The login error was the only one in the app rendered without role="alert".
  defectsAssert.match(read("app/login/page.tsx"), /\{error && <p role="alert"/);
});

defectsTest("removing an admin uses an accessible dialog, not window.confirm", () => {
  const source = read("app/admins/page.tsx");
  // Ignore the comment that explains why it was removed.
  const code = source.split("\n").filter((line: string) => !line.trim().startsWith("*") && !line.trim().startsWith("/*")).join("\n");
  defectsAssert.doesNotMatch(code, /window\.confirm/, "window.confirm is unstyleable and unannounced");
  defectsAssert.match(source, /<dialog/, "use the native dialog pattern this codebase already has");
  defectsAssert.match(source, /requestAnimationFrame\(\(\) => opener\?\.focus\(\)\)/,
    "focus must return to the trigger on close");
});

defectsTest("the audit log requests the full history the server allows", () => {
  // Omitting the limit capped the access log at the server default of 50, silently.
  defectsAssert.match(read("lib/api.ts"), /admin\/org\/audit\?limit=\$\{limit\}/);
});
