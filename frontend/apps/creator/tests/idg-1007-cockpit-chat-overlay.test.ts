import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// IDG-1007: the cockpit chat used to revert to an inline flex column at lg+ (`lg:static`), which
// took permanent horizontal space and squeezed <main> into a narrow strip next to it ("the really
// thin side window"). It must stay a floating overlay at every width, so the tender content keeps
// its full width when the chat is open.
test("cockpit chat panel is a fixed overlay at every breakpoint, never an inline column", () => {
  const src = source("components/cockpit/chat-panel.tsx");
  assert.match(src, /"fixed bottom-0 right-0/);
  assert.match(src, /insetClassName = "top-14"/);
  assert.doesNotMatch(src, /lg:static/);
  // shrink-0 only mattered while it was a flex child; as an overlay it must not reappear.
  const asideClasses = src.slice(src.indexOf("<aside"), src.indexOf("</aside>"));
  assert.doesNotMatch(asideClasses.slice(0, asideClasses.indexOf(">")), /shrink-0/);
});

// An overlay can afford more width than the 300px column could, since it no longer steals layout.
// IDG-1008 made that width user-set, so the 420px is now the default the panel opens at, not a
// hardcoded class.
test("cockpit chat panel widens on desktop", () => {
  const src = source("components/cockpit/chat-panel.tsx");
  assert.match(src, /const DEFAULT_WIDTH = 420/);
  assert.match(src, /lg:w-\[var\(--cockpit-chat-width\)\]/);
});

// The dim backdrop stays mobile-only: at lg+ the panel floats above the content without dimming
// it, so a reviewer can still read and copy from the tender while chatting.
test("cockpit chat backdrop dims only below lg", () => {
  const src = source("components/cockpit/chat-panel.tsx");
  const backdrop = src.slice(src.indexOf("onClick={onClose}"), src.indexOf("<aside"));
  assert.match(backdrop, /bg-black\/50 lg:hidden/);
});

// Both cockpits render the same shared panel, so neither shell should carry its own layout
// assumptions about the chat occupying a column.
test("both cockpit shells render the shared chat panel", () => {
  for (const path of [
    "components/pre-sales/cockpit-shell.tsx",
    "components/sales-intelligence/cockpit-shell.tsx",
  ]) {
    assert.match(source(path), /<CockpitChatPanel/);
  }
});

// An open-by-default overlay would cover the content (and every control under it) on first load
// until dismissed: Sales Intelligence used to start with chatOpen=true and Pre-Sales opened it
// from an lg+ matchMedia effect, both safe only while the panel was an inline column. Four
// desktop e2e specs failed on exactly that (clicks intercepted by the panel). Closed on load in
// both cockpits, opened from the Chat button.
test("neither cockpit opens the chat on first load", () => {
  for (const path of [
    "components/pre-sales/cockpit-shell.tsx",
    "components/sales-intelligence/cockpit-shell.tsx",
  ]) {
    const src = source(path);
    assert.match(src, /const \[chatOpen, setChatOpen\] = useState\(false\)/);
    assert.doesNotMatch(src, /matchMedia/);
    assert.doesNotMatch(src, /setChatOpen\(true\)/);
  }
});
