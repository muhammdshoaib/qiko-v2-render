import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  PASSWORD_RESET_EMAIL_SESSION_KEY,
  clearPasswordResetEmail,
  getPasswordResetSessionStorage,
  normalisePasswordResetEmail,
  resolvePasswordResetEmail,
  storePasswordResetEmail,
} from "../lib/password-reset-session";
import {
  assignableSections,
  isAssignableSection,
} from "../components/pre-sales/section-assignment-utils";
import {
  AI_DRAFTING_DESCRIPTION,
  aiDraftingPercent,
} from "../components/pre-sales/metrics";
import procSections from "./fixtures/proc-sections.json";

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

class ThrowingStorage {
  getItem(): string | null {
    const error = new Error("blocked");
    error.name = "SecurityError";
    throw error;
  }

  setItem(): void {
    const error = new Error("blocked");
    error.name = "SecurityError";
    throw error;
  }

  removeItem(): void {
    throw new Error("storage unavailable");
  }
}

test("password reset email prefers the query, falls back to the session and clears after use", () => {
  const storage = new MemoryStorage();
  storePasswordResetEmail(storage, "  Jake.Example@Qiko.AI ");

  assert.equal(PASSWORD_RESET_EMAIL_SESSION_KEY, "qiko.password-reset.email");
  assert.equal(storage.getItem(PASSWORD_RESET_EMAIL_SESSION_KEY), "jake.example@qiko.ai");
  assert.equal(resolvePasswordResetEmail(" Query.User@Example.COM ", storage), "query.user@example.com");
  assert.equal(resolvePasswordResetEmail("", storage), "jake.example@qiko.ai");
  assert.equal(normalisePasswordResetEmail(" No.Email@Example.COM "), "no.email@example.com");

  clearPasswordResetEmail(storage);
  assert.equal(resolvePasswordResetEmail(null, storage), "");
});

test("password reset storage is best effort when property access, get, set or remove throws", () => {
  const storage = new ThrowingStorage();
  const blockedWindow = {
    get sessionStorage(): ThrowingStorage {
      const error = new Error("property blocked");
      error.name = "SecurityError";
      throw error;
    },
  };

  assert.equal(getPasswordResetSessionStorage(blockedWindow), null);
  assert.doesNotThrow(() => storePasswordResetEmail(null, "Jake@Qiko.AI"));
  assert.equal(storePasswordResetEmail(null, "Jake@Qiko.AI"), "jake@qiko.ai");
  assert.equal(resolvePasswordResetEmail("Query@Qiko.AI", null), "query@qiko.ai");
  assert.equal(resolvePasswordResetEmail(null, null), "");
  assert.doesNotThrow(() => clearPasswordResetEmail(null));

  assert.doesNotThrow(() => storePasswordResetEmail(storage, "Jake@Qiko.AI"));
  assert.equal(resolvePasswordResetEmail("Query@Qiko.AI", storage), "query@qiko.ai");
  assert.doesNotThrow(() => resolvePasswordResetEmail(null, storage));
  assert.equal(resolvePasswordResetEmail(null, storage), "");
  assert.doesNotThrow(() => clearPasswordResetEmail(storage));
});

test("real PROC fixture has 53 nodes, 9 parent groups and exactly 44 leaves", () => {
  const parentIds = new Set(procSections.flatMap((section) => section.parent_id ? [section.parent_id] : []));
  const assignable = assignableSections(procSections);

  assert.equal(procSections.length, 53);
  assert.equal(parentIds.size, 9);
  assert.equal(assignable.length, 44);
  assert.ok(assignable.every((section) => !parentIds.has(section.id)));
  assert.ok(procSections.filter((section) => parentIds.has(section.id)).every(
    (section) => !assignable.some((leaf) => leaf.id === section.id),
  ));
});

test("assignable sections exclude every referenced parent independent of depth", () => {
  const nested = [
    { id: "root", parent_id: null },
    { id: "branch", parent_id: "root" },
    { id: "leaf", parent_id: "branch" },
    { id: "standalone", parent_id: null },
  ];

  assert.deepEqual(assignableSections(nested).map((section) => section.id), ["leaf", "standalone"]);
  assert.equal(isAssignableSection(nested[0], nested), false);
  assert.equal(isAssignableSection(nested[1], nested), false);
  assert.equal(isAssignableSection(nested[2], nested), true);
});

test("AI drafting aggregates totals, ignores invalid totals and clamps completed drafts", () => {
  assert.equal(aiDraftingPercent([
    { gen_status: { drafts: { done: 1, total: 1 } } },
    { gen_status: { drafts: { done: 0, total: 99 } } },
  ]), 1);
  assert.equal(aiDraftingPercent([
    {},
    { gen_status: { drafts: { done: 5, total: 0 } } },
    { gen_status: { drafts: { done: 3, total: 10 } } },
  ]), 30);
  assert.equal(aiDraftingPercent([
    { gen_status: { drafts: { done: 20, total: 10 } } },
    { gen_status: { drafts: { done: -4, total: 10 } } },
  ]), 50);
  assert.equal(aiDraftingPercent([{}, { gen_status: { drafts: { done: 1, total: 0 } } }]), null);
  assert.equal(
    AI_DRAFTING_DESCRIPTION,
    "AI drafting progress is total completed drafts divided by total draftable items across active bids. It does not measure answer quality, confidence, grounding, or KB gaps.",
  );
});

test("UI source pins reset copy and shared helper wiring because no component unit runner exists", () => {
  const forgotSource = readFileSync(resolve(process.cwd(), "app/forgot-password/page.tsx"), "utf8");
  const resetSource = readFileSync(resolve(process.cwd(), "app/reset-password/page.tsx"), "utf8");
  const studioSource = readFileSync(resolve(process.cwd(), "app/studio/page.tsx"), "utf8");
  const landingSource = readFileSync(
    resolve(process.cwd(), "components/pre-sales/worker-landing.tsx"),
    "utf8",
  );

  assert.doesNotMatch(forgotSource, /window\.sessionStorage/);
  assert.doesNotMatch(resetSource, /window\.sessionStorage/);
  assert.match(forgotSource, /getPasswordResetSessionStorage\(window\)/);
  assert.match(forgotSource, /storePasswordResetEmail\(storage, normalisedEmail\);[\s\S]*setLocation/);
  assert.match(resetSource, /resolvePasswordResetEmail\(queryEmail, storage\)/);
  assert.match(resetSource, /clearPasswordResetEmail\(storage\);[\s\S]*setSuccess\(true\)/);
  assert.ok(resetSource.includes(
    "We have sent a reset link to your email. Please check your email, copy the code, and click &quot;Reset Password.&quot;",
  ));
  for (const source of [studioSource, landingSource]) {
    assert.ok(source.includes("aiDraftingPercent"));
    assert.ok(source.includes("AI_DRAFTING_DESCRIPTION"));
    assert.ok(source.includes('label: "AI Drafting"'));
  }
});

test("load smoke and deployment playbooks use the versioned health endpoint", () => {
  const repositoryRoot = resolve(process.cwd(), "../../..");
  const smoke = readFileSync(resolve(repositoryRoot, "loadtest/smoke.js"), "utf8");
  const livePlaybook = readFileSync(resolve(repositoryRoot, "docs/playbooks/live.md"), "utf8");
  const preprodPlaybook = readFileSync(resolve(repositoryRoot, "docs/playbooks/preprod.md"), "utf8");

  assert.ok(smoke.includes("${BASE}/api/v1/health"));
  assert.ok(!smoke.includes("${BASE}/health"));
  for (const playbook of [livePlaybook, preprodPlaybook]) {
    assert.ok(playbook.includes("/api/v1/health"));
    assert.ok(!playbook.split("/api/v1/health").join("").includes("/health"));
  }
});

test("approved email logo asset has the pinned SHA-256 digest", () => {
  const logo = readFileSync(resolve(process.cwd(), "public/qiko-logo-email.png"));
  assert.equal(
    createHash("sha256").update(logo).digest("hex"),
    "b8394003e507ce05771e99424ea1ff4b3b29b343ef14fd4ea3b237bcace45544",
  );
});
