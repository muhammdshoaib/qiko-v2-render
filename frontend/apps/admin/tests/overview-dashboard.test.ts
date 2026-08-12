const ovAssert = require("node:assert/strict");
const { existsSync: ovExists, readFileSync: ovRead } = require("node:fs");
const { resolve: ovResolve } = require("node:path");
const ovTest = require("node:test");

function ovFind(relative: string): string {
  for (let up = 0; up < 8; up += 1) {
    const candidate = ovResolve(__dirname, "../".repeat(up) || ".", relative);
    if (ovExists(candidate)) return candidate;
  }
  throw new Error(`could not locate ${relative}`);
}
const ovPage = ovRead(ovFind("frontend/apps/admin/app/overview/page.tsx"), "utf8");
const ovCharts = ovRead(ovFind("frontend/packages/ui/src/charts.tsx"), "utf8");

ovTest("the charts are drawn rather than pulled from a library", () => {
  // Recharts and its peers are 400kb-plus of runtime for one trend line and two ranked bar lists. The
  // admin app is an internal tool loaded over the public internet by people in a hurry, and a
  // dependency that size has to earn its place by doing something hard.
  const pkg = JSON.parse(ovRead(ovFind("frontend/packages/ui/package.json"), "utf8"));
  const deps = { ...pkg.dependencies, ...pkg.peerDependencies };
  for (const heavy of ["recharts", "chart.js", "victory", "@visx/visx", "d3"]) {
    ovAssert.ok(!(heavy in deps), `${heavy} was added; the charts here do not need it`);
  }
  ovAssert.match(ovCharts, /<svg/);
});

ovTest("every chart is readable without seeing it", () => {
  // The usual casualty of a hand-rolled chart. An SVG with no text is invisible to a screen reader and
  // unreadable to anyone who cannot distinguish the colours, so the figures are also rendered as a
  // hidden table. The table is the content; the drawing is a convenience.
  ovAssert.match(ovCharts, /role="img"/);
  ovAssert.match(ovCharts, /aria-label=\{summary\}/);
  ovAssert.match(ovCharts, /function VisuallyHiddenTable/);
  ovAssert.match(ovCharts, /className="sr-only"/);
  // The summary has to carry numbers, not just a title, or it says nothing a heading did not.
  ovAssert.match(ovCharts, /total \$\{format\(total\)\}, peak \$\{format\(peak\)\}/);
  // And the bar list is a real list with a name, not a stack of divs.
  ovAssert.match(ovCharts, /<ul aria-label=\{label\}/);
});

ovTest("the trend scales from zero", () => {
  // A chart whose axis starts at the lowest value makes a two percent wobble look like a cliff. It is
  // the single most common way a dashboard misleads the person reading it, and it is a one-line
  // decision that nobody revisits.
  ovAssert.match(ovCharts, /const peak = Math\.max\(\.\.\.points\.map\(\(p\) => p\.value\), 0\);/);
  ovAssert.doesNotMatch(ovCharts, /Math\.min\(\.\.\.points\.map/, "no minimum-based baseline");
  // A flat zero series must still draw rather than divide by zero.
  ovAssert.match(ovCharts, /const scale = peak > 0 \? peak : 1;/);
});

ovTest("values are printed, not left to be estimated from bar length", () => {
  // A bar whose length is the only encoding forces the reader to estimate against a scale that is not
  // drawn, and they estimate wrong.
  ovAssert.match(ovCharts, /\{format\(item\.value\)\}/);
});

ovTest("no data hides behind a pointer", () => {
  // A tooltip on hover is unreachable by keyboard and absent on touch.
  ovAssert.doesNotMatch(ovCharts, /onMouseEnter|onMouseOver|onPointerEnter/);
});

ovTest("each block is fetched only when its capability is held", () => {
  // A narrowed admin gets a shorter page rather than a page of errors, and no request is made that
  // would be refused: a 403 in the log is a red herring for whoever reads it next.
  ovAssert.match(ovPage, /enabled: me\.isSuccess && can\("view_ai_cost"\)/);
  ovAssert.match(ovPage, /enabled: me\.isSuccess && can\("view_customers"\)/);
  ovAssert.match(ovPage, /[^!]can\("view_ai_cost"\) &&/);
});

ovTest("a reader who cannot see spend is told it exists", () => {
  // Otherwise a shorter page reads as a platform with no spend rather than as a narrower permission.
  ovAssert.match(ovPage, /!can\("view_ai_cost"\) &&/);
  ovAssert.match(ovPage, /needs? the View AI cost capability/);
});

ovTest("every figure states its window and leads somewhere", () => {
  // "Spend" with no period is a number nobody can act on, and a dashboard that only states numbers
  // makes the reader go and find the list themselves, which is the step they were trying to skip.
  ovAssert.match(ovPage, /hint=\{`last \$\{WINDOW_DAYS\} days`\}/);
  ovAssert.match(ovPage, /subtitle=\{`Last \$\{WINDOW_DAYS\} days, all tenants`\}/);
  for (const href of ["/customers", "/subscriptions", "/tenants", "/ai-cost", "/monitoring"]) {
    ovAssert.ok(ovPage.includes(`"${href}"`), `no route from the overview to ${href}`);
  }
});

ovTest("the plan mix is scaled against the total, not the largest plan", () => {
  // Otherwise three plans of 6, 3 and 2 render as a full bar, a half and a third, which reads as
  // shares of something that does not exist.
  ovAssert.match(ovPage, /max=\{ov\.data\.active_subscriptions \|\| undefined\}/);
});

ovTest("the rankings ask for one page, not the whole directory", () => {
  // This is the top of a ranking. Pulling every row to compute a total the server already returns
  // would be slower and no more correct.
  ovAssert.match(ovPage, /listTenants\("", 1, \{ sort: "earnings", order: "desc" \}\)/);
  ovAssert.match(ovPage, /workerMonitoring\(WINDOW_DAYS, 1, undefined, \{ sort: "calls", order: "desc" \}\)/);
});
