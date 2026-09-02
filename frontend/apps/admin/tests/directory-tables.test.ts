const dirAssert = require("node:assert/strict");
const { existsSync: dirExists, readFileSync: dirRead } = require("node:fs");
const { resolve: dirResolve } = require("node:path");
const dirTest = require("node:test");

function dirFind(relative: string): string {
  for (let up = 0; up < 8; up += 1) {
    const candidate = dirResolve(__dirname, "../".repeat(up) || ".", relative);
    if (dirExists(candidate)) return candidate;
  }
  throw new Error(`could not locate ${relative} from ${__dirname}`);
}
const dirAdmin = "frontend/apps/admin/";
const dirStrip = (source: string) =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const dirShell = dirRead(dirFind(`${dirAdmin}components/directory-page.tsx`), "utf8");
const dirApi = dirRead(dirFind(`${dirAdmin}lib/api.ts`), "utf8");
const DIR_PAGES = {
  customers: dirRead(dirFind(`${dirAdmin}app/customers/page.tsx`), "utf8"),
  tenants: dirRead(dirFind(`${dirAdmin}app/tenants/page.tsx`), "utf8"),
  users: dirRead(dirFind(`${dirAdmin}app/users/page.tsx`), "utf8"),
  workers: dirRead(dirFind(`${dirAdmin}app/workers/page.tsx`), "utf8"),
  monitoring: dirRead(dirFind(`${dirAdmin}app/monitoring/page.tsx`), "utf8"),
  // /subscriptions is the customer directory narrowed by plan, so it shares the allowlist. It was the
  // last list still carrying its own copy of the debounce, pagination and error affordances.
  subscriptions: dirRead(dirFind(`${dirAdmin}app/subscriptions/page.tsx`), "utf8"),
  // The last page still rendering lists as stacks of cards, with its own width and no pagination.
  invoices: dirRead(dirFind(`${dirAdmin}app/invoices/page.tsx`), "utf8"),
};

dirTest("every directory renders the shared table, not a card stack", () => {
  // The console rendered all five lists as stacks of cards: no column headers, nothing sortable, and a
  // screen reader received an unlabelled stream of values.
  for (const [name, source] of Object.entries(DIR_PAGES)) {
    dirAssert.match(source, /DirectoryPage</, `${name} must use the shared shell`);
    dirAssert.match(source, /columns/, `${name} must declare columns`);
    dirAssert.doesNotMatch(source, /renderRow=/, `${name} still renders rows by hand`);
  }
  dirAssert.match(dirShell, /<DataTable/);
});

dirTest("search, page and sort live in the URL", () => {
  // A directory link is what an operator pastes into a ticket. Internal state cannot be shared, and it
  // also breaks the back button.
  dirAssert.match(dirShell, /useSearchParams\(\)/);
  dirAssert.match(dirShell, /params\.get\("q"\)/);
  dirAssert.match(dirShell, /params\.get\("page"\)/);
  dirAssert.match(dirShell, /params\.get\("sort"\)/);
  dirAssert.match(dirShell, /router\.replace\(`\?\$\{next\.toString\(\)\}`/);
});

dirTest("only the search input keeps local state, and it syncs back from the URL", () => {
  // The input must stay responsive between keystrokes, so it is the one exception. It has to follow the
  // URL afterwards or a shared link shows the wrong text in the box.
  const code = dirStrip(dirShell);
  dirAssert.match(code, /const \[typed, setTyped\] = useState\(urlSearch\)/);
  dirAssert.match(code, /useEffect\(\(\) => \{ setTyped\(urlSearch\); \}, \[urlSearch\]\)/);
});

dirTest("a search or sort change resets to page one", () => {
  // Otherwise the operator lands on an empty page and reads it as "no results" when there are results
  // on page 1. Page 3 of one ordering is also not page 3 of another.
  dirAssert.match(dirShell, /setParam\(\{ q: typed\.trim\(\), page: "" \}\)/);
  dirAssert.match(dirShell, /setParam\(\{ sort: nextSort, order: nextOrder, page: "" \}\)/);
});

dirTest("no column claims a sort the server will refuse", () => {
  // The server validates the key against a per-endpoint allowlist and returns 422 for anything else, so
  // a column marked sortable that the allowlist omits is a control that errors when used.
  const allowlists = dirApi.slice(dirApi.indexOf("export const SORTABLE"));
  for (const [name, source] of Object.entries(DIR_PAGES)) {
    const listed = allowlists.slice(allowlists.indexOf(`${name}:`));
    const allowed = [...listed.slice(0, listed.indexOf("]")).matchAll(/"(\w+)"/g)].map((m) => m[1]);
    dirAssert.ok(allowed.length > 0, `${name} declares no sortable keys`);

    // Each `{ id: "x", ... sortable: true` in the page must appear in that list.
    const columnBlocks = source.split(/\{\s*\n?\s*id: "/).slice(1);
    for (const block of columnBlocks) {
      const id = block.slice(0, block.indexOf('"'));
      const head = block.slice(0, block.indexOf("cell:"));
      if (/sortable: true/.test(head)) {
        dirAssert.ok(allowed.includes(id),
          `${name} marks "${id}" sortable but the server allowlist is [${allowed.join(", ")}]`);
      }
    }
  }
});

dirTest("the sort actually reaches the API", () => {
  // The backend has accepted sort and order on all five endpoints since leg B and no page ever sent
  // one, so a validated allowlisted sort existed on the server and was unreachable from the product.
  dirAssert.match(dirApi, /const applySort = \(params: URLSearchParams, sort\?: ListSort\)/);
  dirAssert.match(dirApi, /params\.set\("sort", sort\.sort\)/);
  dirAssert.match(dirApi, /params\.set\("order", sort\.order\)/);
  dirAssert.match(dirShell, /fetchPage\(urlSearch, page, sort\)/);
  dirAssert.match(dirShell, /queryKey: \[queryKey, urlSearch, page, filterToken, sortKey, order\]/);
});

dirTest("filters narrow on the server, not after the fetch", () => {
  // Filtering client-side leaves the total describing the unfiltered set, so the page count and the
  // "showing N of M" line are both wrong. That is the class of bug this leg started from.
  dirAssert.doesNotMatch(DIR_PAGES.monitoring, /\.filter\(\(w\) => w\.enabled/,
    "availability must be a server filter");
  dirAssert.match(DIR_PAGES.monitoring, /availability === "" \? undefined : availability === "true"/);
  dirAssert.match(DIR_PAGES.workers, /status \|\| undefined/);
  dirAssert.match(DIR_PAGES.users, /\{ role, twofa \}/);
});

dirTest("the heading announces a range, not a bare total", () => {
  // "137 total" is identical before and after a filter that returns the same count of a different set,
  // so a live region announces nothing.
  dirAssert.match(dirShell, /Showing \$\{firstOnPage\}-\$\{\(effectivePage - 1\) \* pageSize \+ shown\} of \$\{total\}/);
  dirAssert.match(dirShell, /aria-live="polite"/);
});

dirTest("rows dim rather than disappearing while the next page loads", () => {
  dirAssert.match(dirShell, /placeholderData: keepPreviousData/);
  dirAssert.match(dirShell, /stale=\{rows\.isPlaceholderData\}/);
});

dirTest("the empty state distinguishes filtered from genuinely empty", () => {
  for (const [name, source] of Object.entries(DIR_PAGES)) {
    dirAssert.match(source, /emptyMessage=\{\(filtered\) =>/, `${name} needs both messages`);
  }
  dirAssert.match(dirShell, /emptyMessage\(narrowed\)/);
});

dirTest("the customers table omits the columns its endpoint does not return", () => {
  // /admin/customers returns no user or worker counts, and the server refuses to sort by them for the
  // same reason: ordering by a field the response omits discloses that field's ordering without ever
  // showing it. Those columns belong on /tenants.
  dirAssert.doesNotMatch(DIR_PAGES.customers, /id: "users"/);
  dirAssert.doesNotMatch(DIR_PAGES.customers, /id: "workers"/);
  dirAssert.match(DIR_PAGES.tenants, /id: "users"[\s\S]{0,80}sortable: true/);
});

dirTest("the spend column is absent rather than blank without the capability", () => {
  // An empty cell reads as "this worker cost nothing".
  dirAssert.match(DIR_PAGES.monitoring, /costVisible \? \[\{/);
  dirAssert.match(DIR_PAGES.monitoring, /view_ai_cost/);
});

dirTest("each table declares a default sort matching the endpoint's own order", () => {
  // Otherwise the header shows no active sort while the rows are in a specific order the operator
  // cannot account for.
  dirAssert.match(DIR_PAGES.tenants, /defaultSort=\{\{ sort: "earnings", order: "desc" \}\}/);
  dirAssert.match(DIR_PAGES.customers, /defaultSort=\{\{ sort: "earnings", order: "desc" \}\}/);
  dirAssert.match(DIR_PAGES.monitoring, /defaultSort=\{\{ sort: "calls", order: "desc" \}\}/);
});

dirTest("the empty state cannot render before the list has been asked for", () => {
  // Found by opening the page rather than by reading it. React reported a hydration mismatch on
  // /customers: the server rendered "No customers yet." and the client rendered skeletons.
  //
  // The cause is a React Query v5 detail with a real consequence. The rows query is gated on the
  // capability check with `enabled: me.isSuccess`, and a DISABLED query reports isLoading FALSE, because
  // it is not loading, it has not started. So `rows.isLoading ? skeletons : table` fell through to the
  // table, which fell through to its empty state, and the page asserted there were no customers before
  // it had asked. On a slow connection a real operator saw "No customers yet" and then the list.
  //
  // An empty state that lies is worse than a spinner. This is the third shape of that same mistake in
  // this console, after the filtered-versus-genuinely-empty message and the blank spend column.
  dirAssert.match(dirShell, /const awaitingFirstAnswer = !me\.isSuccess \|\| rows\.isLoading/);
  // Both the announcement and the body have to use it, or one of them still lies.
  dirAssert.match(dirShell, /\{awaitingFirstAnswer \? `Loading \$\{noun\}\.\.\.`/);
  dirAssert.match(dirShell, /\{awaitingFirstAnswer\s*\n?\s*\? <div className="space-y-2">/);
  // And nothing may go back to keying the body on isLoading alone.
  const body = dirShell.slice(dirShell.indexOf("const awaitingFirstAnswer"));
  dirAssert.doesNotMatch(body, /\{rows\.isLoading\s*$/m, "the raw flag must not gate the body again");
});

dirTest("the page size is sent to the server, not assumed", () => {
  // The old constant carried a comment saying it MUST match pagination.PAGE_SIZE on the server. That is
  // an agreement between two files in two languages with nothing enforcing it: the day the server default
  // changes, every range and page count in the console is silently wrong, and wrong in a way that looks
  // plausible. "Showing 1-20 of 137" over pages of ten is not an error anyone reports, it is just a
  // console nobody quite trusts.
  dirAssert.match(dirApi, /export const DIRECTORY_PAGE_SIZE = 10;/);
  dirAssert.match(dirApi, /page_size: String\(DIRECTORY_PAGE_SIZE\)/);
  // Both paths: the shared helper and the customers endpoint, which builds its own params.
  const sent = [...dirApi.matchAll(/page_size: String\(DIRECTORY_PAGE_SIZE\)/g)].length;
  dirAssert.ok(sent >= 2, `page_size is sent from ${sent} places, expected the helper and customers`);
});

dirTest("the range and page count come from what the server applied", () => {
  // The server clamps page_size to its own maximum and falls back on a nonsensical value. If it applies
  // something other than what was asked for, arithmetic based on the request is wrong.
  dirAssert.match(dirShell, /const pageSize = rows\.data\?\.page_size \|\| DIRECTORY_PAGE_SIZE;/);
  dirAssert.match(dirShell, /Math\.ceil\(total \/ pageSize\)/);
  dirAssert.match(dirShell, /\(effectivePage - 1\) \* pageSize \+ 1/);
  // No local mirror of the server's default may come back.
  dirAssert.doesNotMatch(dirShell, /const PAGE_SIZE = \d+/, "no second source of truth for the size");
});

dirTest("QIKO-1044: the displayed page follows the server's clamp, not the URL's request", () => {
  // The server clamps an out-of-range page (?page=100 with only 5 pages exist) and reports the clamped
  // value in rows.data.page. Computing the range or handing the Pagination control the raw URL `page`
  // instead shows a range like "991-... of 50": the right total, computed from the wrong page.
  dirAssert.match(dirShell, /const effectivePage = rows\.data\?\.page \?\? page;/);
  dirAssert.match(dirShell, /\(effectivePage - 1\) \* pageSize \+ shown/);
  dirAssert.match(dirShell, /<Pagination page=\{effectivePage\}/);
  // The raw URL-requested page must still be what is actually sent to the server.
  dirAssert.match(dirShell, /queryFn: \(\) => fetchPage\(urlSearch, page, sort\)/);
});

dirTest("payment links are a table but not a directory", () => {
  // They are looked up per email rather than browsed, so they get the table without search, sort and
  // pagination wrapped around them. Consistency means the same components, not the same chrome
  // regardless of whether it makes sense.
  dirAssert.match(DIR_PAGES.invoices, /<DataTable\s*\n?\s*caption="Payment links/);
  dirAssert.match(DIR_PAGES.invoices, /enabled: email\.includes\("@"\)/);
  // And the table only appears once a lookup has run: its empty state before an email is entered would
  // say "no payment links" about a customer nobody has named.
  dirAssert.match(DIR_PAGES.invoices, /\{links\.isSuccess && \(/);
});

dirTest("no list in the console renders as a stack of cards any more", () => {
  // Consistency here is not cosmetics. An operator who has learned that every list has sortable headers
  // and a shareable URL loses that everywhere the moment one page does not, because they stop trusting
  // the pattern rather than noting the exception.
  for (const [name, source] of Object.entries(DIR_PAGES)) {
    dirAssert.doesNotMatch(source, /\.map\(\([a-z]+\) => \(\s*\n?\s*<Card/,
      `${name} still renders rows as cards`);
  }
});
