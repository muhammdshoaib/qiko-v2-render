import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolve } from "node:path";

import {
  BEHAVIOR_MAX_CONTENT,
  BEHAVIOR_MAX_ENTRIES,
  BEHAVIOR_MAX_TITLE,
  normalizeBehaviorEntries,
  removeBehaviorEntry,
  serializeBehaviorEntries,
  upsertBehaviorEntry,
  validateBehaviorEntry,
} from "../lib/behavior-config";

test("behavior config normalizes legacy and canonical entries and serializes the canonical shape", () => {
  assert.deepEqual(normalizeBehaviorEntries([]), []);

  const legacyScalar = normalizeBehaviorEntries("Greet every customer by name.");
  assert.equal(legacyScalar.length, 1);
  assert.ok(legacyScalar[0].id);
  assert.equal(legacyScalar[0].title, "Greet every customer by name.");
  assert.equal(legacyScalar[0].content, "");

  const entries = normalizeBehaviorEntries([
    "Confirm what the customer needs before answering.",
    { id: "rule-escalation", title: "Escalation", content: "Escalate refund requests." },
    { id: "guardrail-pii", title: "Personal data", description: "Never expose personal data." },
  ]);

  assert.deepEqual(entries.map((entry: { title: string; content: string }) => ({
    title: entry.title,
    content: entry.content,
  })), [
    { title: "Confirm what the customer needs before answering.", content: "" },
    { title: "Escalation", content: "Escalate refund requests." },
    { title: "Personal data", content: "Never expose personal data." },
  ]);
  assert.equal(entries[1].id, "rule-escalation");
  assert.equal(entries[2].id, "guardrail-pii");
  assert.deepEqual(serializeBehaviorEntries(entries), [
    { id: entries[0].id, title: "Confirm what the customer needs before answering.", content: "" },
    { id: "rule-escalation", title: "Escalation", content: "Escalate refund requests." },
    { id: "guardrail-pii", title: "Personal data", content: "Never expose personal data." },
  ]);
});

test("behavior config rebases item updates and exposes matching client limits", () => {
  const first = { id: "one", title: "First", content: "First content" };
  const second = { id: "two", title: "Second", content: "Second content" };
  assert.deepEqual(upsertBehaviorEntry([first], second), [first, second]);
  assert.deepEqual(upsertBehaviorEntry([first, second], { ...first, content: "Updated" }), [
    { ...first, content: "Updated" }, second,
  ]);
  assert.deepEqual(removeBehaviorEntry([first, second], "one"), [second]);
  assert.equal(validateBehaviorEntry(first), null);
  assert.match(validateBehaviorEntry({ ...first, title: "" }) ?? "", /title/i);
  assert.match(validateBehaviorEntry({ ...first, content: "" }) ?? "", /content/i);
  assert.equal(BEHAVIOR_MAX_ENTRIES, 50);
  assert.equal(BEHAVIOR_MAX_TITLE, 255);
  assert.equal(BEHAVIOR_MAX_CONTENT, 4000);
});

test("behavior UI binds structured fields, limits, save and confirmed deletion", () => {
  const source = readFileSync(resolve(process.cwd(), "app/workers/[id]/page.tsx"), "utf8");
  assert.match(source, /maxLength=\{BEHAVIOR_MAX_TITLE\}/);
  assert.match(source, /maxLength=\{BEHAVIOR_MAX_CONTENT\}/);
  assert.match(source, /all\.length >= BEHAVIOR_MAX_ENTRIES/);
  // QIKO-1063: window.confirm is unstyleable and unannounced to assistive tech. Deleting a saved
  // behavior entry now goes through the shared accessible confirmation dialog instead.
  assert.doesNotMatch(source, /window\.confirm/);
  assert.match(source, /openConfirmationDialog\(/);
  assert.match(source, /upsertBehaviorEntry/);
  assert.match(source, /removeBehaviorEntry/);
});
