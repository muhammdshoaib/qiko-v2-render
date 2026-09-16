import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

const PANEL = "components/cockpit/chat-panel.tsx";

// IDG-1008: the desktop width was a flat lg:w-[420px] guess baked into the component. It is now
// user-set, so the class has to consume the live value; an inline width would beat the class at
// every breakpoint, including the sub-lg touch drawer that must stay 86vw-capped.
test("desktop width comes from a custom property the lg class consumes", () => {
  const src = source(PANEL);
  assert.match(src, /"--cockpit-chat-width": `\$\{width\}px`/);
  assert.match(src, /lg:w-\[var\(--cockpit-chat-width\)\]/);
  assert.doesNotMatch(src, /lg:w-\[420px\]/);
  // The sub-lg drawer keeps its own width and viewport cap.
  assert.match(src, /w-\[300px\]/);
  assert.match(src, /max-w-\[86vw\]/);
});

// Clamped: a panel draggable to 20px or over the whole viewport is worse than a fixed one.
test("width is clamped between a readable minimum and a non-covering maximum", () => {
  const src = source(PANEL);
  assert.match(src, /const MIN_WIDTH = 300/);
  assert.match(src, /const MAX_WIDTH = 720/);
  assert.match(src, /function clampWidth\(width: number\): number \{\s*return Math\.min\(MAX_WIDTH, Math\.max\(MIN_WIDTH, Math\.round\(width\)\)\);/);
  // Every path that sets a width goes through the clamp, drag and keyboard alike.
  assert.match(src, /persistWidth\(clampWidth\(startWidth \+ \(startX - move\.clientX\)\)\)/);
  assert.match(src, /persistWidth\(clampWidth\(width \+ step\)\)/);
});

// Without persistence every session starts by resizing again.
test("the chosen width survives close, reopen and reload", () => {
  const src = source(PANEL);
  assert.match(src, /const WIDTH_STORAGE_KEY = "qiko\.cockpitChatWidth"/);
  assert.match(src, /window\.localStorage\.setItem\(WIDTH_STORAGE_KEY/);
  // Restored in an effect, not a lazy initialiser: localStorage does not exist during SSR and
  // reading it in the first client render would disagree with the server's.
  const restore = src.slice(src.indexOf("useState(DEFAULT_WIDTH)"), src.indexOf("function persistWidth"));
  assert.match(restore, /useEffect\(\(\) => \{[\s\S]*getItem\(WIDTH_STORAGE_KEY\)/);
  assert.match(restore, /Number\.isFinite\(stored\) && stored > 0/);
  // A blocked localStorage must not break resizing.
  assert.match(src, /setItem\(WIDTH_STORAGE_KEY, String\(next\)\);\s*\} catch \{/);
});

// A 3px edge is not a touch target, and below lg the panel is a full-height drawer anyway.
test("the resize handle is desktop-only and accessible", () => {
  const src = source(PANEL);
  const handle = src.slice(src.indexOf("onPointerDown={startResize}"), src.indexOf("<div className=\"flex shrink-0 items-center justify-between"));
  assert.match(handle, /role="separator"/);
  assert.match(handle, /aria-orientation="vertical"/);
  assert.match(handle, /aria-label="Resize chat panel"/);
  assert.match(handle, /aria-valuenow=\{width\}/);
  assert.match(handle, /aria-valuemin=\{MIN_WIDTH\}/);
  assert.match(handle, /aria-valuemax=\{MAX_WIDTH\}/);
  assert.match(handle, /tabIndex=\{0\}/);
  assert.match(handle, /hidden w-1\.5 .*lg:block/);
  assert.match(handle, /cursor-col-resize/);
});

// A drag that outruns the 3px handle, or leaves the window, must keep resizing and still end on
// release: that is what pointer capture is for, and why this is not a mousemove-on-window listener.
test("dragging uses pointer capture and does not select the transcript", () => {
  const src = source(PANEL);
  assert.match(src, /setPointerCapture\(event\.pointerId\)/);
  assert.match(src, /releasePointerCapture\(event\.pointerId\)/);
  assert.match(src, /removeEventListener\("pointercancel", onUp\)/);
  assert.match(src, /resizing && "select-none"/);
});

// Arrow keys on a focused separator are the keyboard equivalent of the drag.
test("arrow keys resize the panel in both directions", () => {
  const src = source(PANEL);
  assert.match(src, /const KEYBOARD_STEP = 24/);
  assert.match(src, /event\.key === "ArrowLeft" \? KEYBOARD_STEP/);
  assert.match(src, /event\.key === "ArrowRight" \? -KEYBOARD_STEP/);
  // Any other key falls through untouched, so typing elsewhere is unaffected.
  assert.match(src, /if \(!step\) return;/);
});
