const auditAssert = require("node:assert/strict");
const { existsSync: auditExists, readFileSync: auditRead } = require("node:fs");
const { resolve: auditResolve } = require("node:path");
const auditTest = require("node:test");

function auditFind(relative: string): string {
  for (let up = 0; up < 8; up += 1) {
    const candidate = auditResolve(__dirname, "../".repeat(up) || ".", relative);
    if (auditExists(candidate)) return candidate;
  }
  throw new Error(`could not locate ${relative} from ${__dirname}`);
}
const base = "frontend/apps/admin/";
const page = auditRead(auditFind(`${base}app/audit/page.tsx`), "utf8");
/** Source with comments removed. Four times now a source-reading test in this programme has failed on
 *  the comment explaining the very decision it was checking for, so absence checks use this. */
const stripComments = (source: string) =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const pageCode = stripComments(page);
const detail = auditRead(auditFind(`${base}components/audit-detail.tsx`), "utf8");
const format = auditRead(auditFind(`${base}lib/audit-format.ts`), "utf8");
const shell = auditRead(auditFind(`${base}components/app-shell.tsx`), "utf8");

auditTest("filter state lives in the URL, not in component state", () => {
  // The most used feature of an audit viewer in practice is being sent a link. State mirrored into
  // useState alongside the URL is how a shared link fails to reproduce what the sender was looking at.
  auditAssert.match(page, /useSearchParams\(\)/);
  auditAssert.match(page, /router\.replace\(`\/audit\?\$\{next\.toString\(\)\}`\)/);
  auditAssert.doesNotMatch(pageCode, /useState<string>\(params\.get/,
    "reading a filter into state creates a second source of truth");
});

auditTest("changing a filter discards the cursors built against the old one", () => {
  // A keyset cursor encodes a position within one filtered ordering. Reusing it after the filter
  // changes silently returns rows from the middle of a different result set.
  const setFilter = page.slice(page.indexOf("const setFilter"), page.indexOf("const cursor ="));
  auditAssert.match(setFilter, /setCursors\(\[null\]\)/);
});

auditTest("the list has no total and no page numbers", () => {
  // A COUNT over a filtered multi-million-row table is what makes these pages unusable, and the number
  // is not worth a full scan.
  auditAssert.doesNotMatch(pageCode, /\btotal\b/, "the endpoint deliberately returns no total");
  auditAssert.doesNotMatch(pageCode, /Math\.ceil\(/, "no page count can be derived without a total");
  auditAssert.match(page, /has_more/);
  auditAssert.match(page, /next_cursor/);
});

auditTest("the reader is told when events are hidden from them", () => {
  // Otherwise an operator without the spend capability concludes no cost cap was ever changed, which is
  // a worse outcome than being refused.
  auditAssert.match(page, /hidden_actions/);
  auditAssert.match(page, /hidden\s*\n?\s*from you|hidden[\s\S]{0,40}from you/);
});

auditTest("rows are kept on screen while the next page loads", () => {
  auditAssert.match(page, /placeholderData: keepPreviousData/);
  auditAssert.match(page, /stale=\{events\.isPlaceholderData\}/);
});

auditTest("the empty state distinguishes filtered from genuinely empty", () => {
  auditAssert.match(page, /No events match these filters/);
  auditAssert.match(page, /No events recorded in this window/);
  // And the third case, which is neither: automated actors are hidden.
  auditAssert.match(page, /Automated actors are hidden/);
});

auditTest("the retention policy is stated on the page", () => {
  // Prevents the "the log is missing data" ticket, and shows an auditor the policy is visible to the
  // people who use it. Read from the API so it cannot drift from what the cron enforces.
  auditAssert.match(page, /retention\.data/);
  auditAssert.match(page, /event_retention_days/);
  auditAssert.doesNotMatch(pageCode, /13 months/, "the number must come from the server, not the markup");
});

auditTest("the nav entry is gated on view_audit", () => {
  auditAssert.match(shell, /href: "\/audit"[^}]*requires: "view_audit"/);
});

auditTest("the drawer leads with the sentence the server rendered", () => {
  // Never re-rendered client-side: a sentence rebuilt from current labels would change retroactively
  // when something is renamed, which is the opposite of an audit record.
  auditAssert.match(detail, /id="audit-detail-title"[\s\S]{0,80}headline\(event\)/);
  auditAssert.match(format, /export const headline = \(event: AuditEvent\): string => event\.message/);
});

auditTest("the reason sits above the diff", () => {
  // Operators care about why more than about which field moved.
  auditAssert.ok(detail.indexOf("event.reason") < detail.indexOf("What changed"));
  auditAssert.match(detail, /<blockquote/);
});

auditTest("the diff is a table, not two JSON blobs", () => {
  auditAssert.match(detail, /<th scope="col"[^>]*>Field</);
  auditAssert.match(detail, /<th scope="col"[^>]*>From</);
  auditAssert.match(detail, /<th scope="col"[^>]*>To</);
  auditAssert.match(detail, /<th scope="row"/, "the field name is the row header");
});

auditTest("the request id refilters the list rather than being decoration", () => {
  // A multi-step admin action produces several rows; seeing them as one operation is what an operator
  // reaches for during an incident.
  auditAssert.match(detail, /onFilter\("request", event\.request_id!\)/);
  auditAssert.match(detail, /Show everything from that request/);
});

auditTest("the raw JSON is last and collapsed", () => {
  auditAssert.ok(detail.indexOf("Context") < detail.indexOf("Raw event"));
  auditAssert.match(detail, /<summary[^>]*>Raw event<\/summary>/);
});

auditTest("money is money and booleans read as states", () => {
  auditAssert.match(format, /style: "currency", currency: "USD"/);
  auditAssert.match(format, /NANO_USD_FIELDS/);
  auditAssert.match(format, /value \? "Available" : "Unavailable"/);
  auditAssert.match(format, /value \? "On" : "Off"/);
});

auditTest("a null value renders as an explicit dash, not an empty cell", () => {
  // An empty cell reads as "we did not record this" when the truth is "there was no value".
  auditAssert.match(format, /if \(value === null \|\| value === undefined\) return "-";/);
});

auditTest("credential fields never render a value-shaped placeholder", () => {
  // A masked placeholder invites a reader to believe there is something to reveal. The audit holds no
  // credential values at all, so the field NAME is the entire content.
  auditAssert.match(format, /SECRET_FIELDS/);
  auditAssert.doesNotMatch(format, /\*{4,}/, "no asterisk mask");
  auditAssert.doesNotMatch(format, /slice\(0, ?\d\)\s*\+\s*"\.\.\."/, "no truncated-secret preview");
});

auditTest("platform scope is shown as a value, not as missing data", () => {
  auditAssert.match(page, /Platform<\/span>/);
  auditAssert.match(detail, /Platform-wide/);
});

auditTest("both timezones appear in the drawer, each labelled", () => {
  // Every auditor conversation is in UTC and every operator thinks in local time.
  auditAssert.match(detail, /formatWhen\(event\.occurred_at\)/);
  auditAssert.match(detail, /formatWhenUtc\(event\.occurred_at\)/);
  auditAssert.match(format, /UTC`/);
});

auditTest("impersonation shows the initiator as the actor and the subject separately", () => {
  // Conflating the two is what makes an audit useless in the situation it exists for.
  auditAssert.match(detail, /On behalf of/);
  auditAssert.ok(detail.indexOf("Actor") < detail.indexOf("On behalf of"));
});
