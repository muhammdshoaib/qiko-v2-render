import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1013: finance chat answers were losing bullet and table formatting because the markdown
// renderer did not enable GitHub-Flavored Markdown and had no styled table components.
test("chat markdown enables tables and bullet lists", () => {
  const src = source("components/chat-message.tsx");
  assert.match(src, /import\s+remarkGfm\s+from\s+["']remark-gfm["']/);
  assert.match(src, /remarkPlugins=\{\[remarkGfm\]\}/);
  assert.match(src, /table:\s*\(\{\s*children\s*\}\)/);
  assert.match(src, /thead:/);
  assert.match(src, /tbody:/);
  assert.match(src, /tr:/);
  assert.match(src, /th:/);
  assert.match(src, /td:/);
});
