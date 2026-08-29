import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), "utf8");
}

// EL-1015: the Finance History tab rendered assistant messages as raw text
// (`<p className="whitespace-pre-wrap">{row.content}</p>`), unlike the live chat panel which
// already renders markdown via ChatBubble/AnswerMarkdown (EL-1013). A markdown table or bullet
// list stored in history therefore showed literal `**`/`-`/`|` characters instead of formatting.
test("finance history bubble renders assistant messages as markdown, not raw pre-wrapped text", () => {
  const src = source("components/finance/history-panel.tsx");
  assert.match(src, /import\s*\{\s*AnswerMarkdown\s*\}\s*from\s*["']@\/components\/chat-message["']/);
  const bubble = src.slice(src.indexOf("function HistoryBubble"));
  assert.match(bubble, /isUser\s*\?[\s\S]*?:\s*[\s\S]*?<AnswerMarkdown\s+text=\{row\.content\}\s*\/>/);
});
