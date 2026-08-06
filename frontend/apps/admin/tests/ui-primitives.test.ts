const primAssert = require("node:assert/strict");
const { existsSync: primExists, readFileSync: primRead } = require("node:fs");
const { resolve: primResolve } = require("node:path");
const primTest = require("node:test");

// The design system had 12 components and no Table, Select, Dialog, Checkbox or Pagination, which is
// why every list in the console was cards with no filters: there were no primitives to build anything
// else from. These tests pin the properties that make the new ones worth having.
const primCandidates = [
  primResolve(__dirname, "../../../packages/ui/src"),
  primResolve(__dirname, "../../../../packages/ui/src"),
];
const uiDir = primCandidates.find((dir) => primExists(dir));
primAssert.ok(uiDir, `could not locate @qiko/ui src, tried: ${primCandidates.join(", ")}`);
const primReadUi = (file: string) => primRead(primResolve(uiDir, file), "utf8");
const table = primReadUi("data-table.tsx");
const controls = primReadUi("controls.tsx");
const index = primReadUi("index.tsx");

primTest("the table is semantic markup, not divs with roles", () => {
  // W3C is explicit that native table markup is strongly preferred, and the whole admin app had
  // literally zero of it: no column headers, no scope, so a screen reader got an unlabelled stream.
  for (const tag of ["<table", "<thead", "<tbody", "<tr", "<th", "<td", "<caption"]) {
    primAssert.match(table, new RegExp(tag), `the table must render a real ${tag}`);
  }
  primAssert.doesNotMatch(table, /role="table"|role="grid"/,
    "a div grid would oblige us to the whole composite-widget keyboard model for no gain");
});

primTest("headers carry scope and the identifying cell is a row header", () => {
  primAssert.match(table, /scope="col"/, "every column header needs scope");
  primAssert.match(table, /scope="row"/, "the identifying cell must be a row header");
});

primTest("aria-sort lives on the header cell and only one can be active", () => {
  // Per the ARIA practices: aria-sort goes on the columnheader, never the table, and exactly one
  // header carries a non-none value at a time.
  primAssert.match(table, /aria-sort=/);
  primAssert.match(table, /const active = Boolean\(sort\) && sort === column\.id/,
    "activeness must be derived from the single current sort key");
  primAssert.doesNotMatch(table, /<table[^>]*aria-sort/, "aria-sort must not be on the table");
});

primTest("the sort control is a real button filling its header cell", () => {
  primAssert.match(table, /<button[\s\S]*?onClick=\{\(\) => onSortChange/,
    "sorting must be a button, not a click handler on the th");
  primAssert.match(table, /w-\[calc\(100%\+1rem\)\]/,
    "the button should fill the cell so the whole header is the target");
});

primTest("the sort direction cue is not colour alone", () => {
  // Windows High Contrast strips colour; a glyph survives it.
  primAssert.match(table, /\\u25BC|\\u25B2/, "use a character for the direction indicator");
});

primTest("the table is named for assistive technology", () => {
  primAssert.match(table, /<caption className="sr-only">/);
  primAssert.match(table, /caption: string;/, "caption is required, not optional");
});

primTest("narrow viewports get cards, not a seven-column table", () => {
  primAssert.match(table, /md:hidden/, "cards below the breakpoint");
  primAssert.match(table, /hidden[\s\S]*?md:block/, "table from md up");
});

primTest("the dialog keeps the focus behaviour the console already had right", () => {
  // Native <dialog> gives the focus trap and background inertness for free. What has to be written is
  // the restore, and this is the part hand-rolled modals get wrong.
  primAssert.match(controls, /showModal\(\)/);
  primAssert.match(controls, /requestAnimationFrame\(\(\) => opener\?\.focus\(\)\)/,
    "focus must return to the opener, after a frame");
  primAssert.match(controls, /onCancel=\{\(event\) => \{ if \(busy\) event\.preventDefault\(\); \}\}/,
    "Escape must not abandon a mutation in flight");
});

primTest("controls are native elements so they keep platform behaviour", () => {
  primAssert.match(controls, /<select/, "a native select gets keyboard type-ahead and a mobile picker");
  primAssert.match(controls, /type="checkbox"/);
  primAssert.match(controls, /<textarea/);
  primAssert.match(controls, /<dialog/);
});

primTest("the alert tone chooses its own aria role", () => {
  // Leaving role to the call site is how half the existing notices ended up as plain paragraphs.
  primAssert.match(controls, /role=\{tone === "error" \? "alert" : "status"\}/);
});

primTest("the segmented filter announces its state", () => {
  primAssert.match(controls, /role="group"/);
  primAssert.match(controls, /aria-pressed=\{value === option\.value\}/);
});

primTest("pagination announces a range, not just a total", () => {
  // "137 total" is identical before and after a filter returning the same count of a different set,
  // so a live region announces nothing.
  primAssert.match(controls, /aria-label=\{`\$\{label\} pagination`\}/);
  primAssert.match(controls, /to \{first \+ Math\.max\(0, shown - 1\)\} of \{total\}/);
});

primTest("interactive primitives keep the 44px touch target", () => {
  for (const match of [/h-11/, /min-h-11/]) {
    primAssert.match(controls, match);
  }
});

primTest("the package has no circular import and no new dependency", () => {
  // index re-exports the component files, so those files must not import from index.
  primAssert.doesNotMatch(controls, /from "\.\/index"/);
  primAssert.doesNotMatch(table, /from "\.\/index"/);
  primAssert.match(controls, /from "\.\/cn"/);
  // This package is transpiled into BOTH apps, so anything added here lands in the creator bundle.
  // Checked against IMPORT lines rather than any mention, because the module docstrings discuss why
  // these libraries were considered and rejected.
  const importLines = [table, controls].flatMap((source) =>
    source.split("\n").filter((line: string) => /^\s*import\s/.test(line)));
  for (const forbidden of ["@radix-ui", "@tanstack/react-table", "ag-grid", "@mui/"]) {
    primAssert.ok(!importLines.some((line: string) => line.includes(forbidden)),
      `${forbidden} must not be imported by a package that ships into both apps`);
  }
});

primTest("everything is reachable from the package entry point", () => {
  for (const name of ["DataTable", "Select", "Checkbox", "Textarea", "Alert", "SegmentedFilter",
                      "Dialog", "Pagination"]) {
    primAssert.match(index, new RegExp(`\\b${name}\\b`), `${name} must be exported from index`);
  }
});
