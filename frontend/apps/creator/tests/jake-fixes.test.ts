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
  activeBidPacks,
  aiDraftingPercent,
  knowledgeChunkCount,
  nextBidDeadline,
} from "../components/pre-sales/metrics";
import {
  LOSS_REASONS,
  buildOutcomePayload,
  outcomeDraftIsValid,
} from "../components/pre-sales/outcome-utils";
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
  storePasswordResetEmail(storage, "  Jake.Example@Invalid ");

  assert.equal(PASSWORD_RESET_EMAIL_SESSION_KEY, "qiko.password-reset.email");
  assert.equal(storage.getItem(PASSWORD_RESET_EMAIL_SESSION_KEY), "jake.example@invalid");
  assert.equal(resolvePasswordResetEmail(" Query.User@Invalid ", storage), "query.user@invalid");
  assert.equal(resolvePasswordResetEmail("", storage), "jake.example@invalid");
  assert.equal(normalisePasswordResetEmail(" No.Email@Invalid "), "no.email@invalid");

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
  assert.doesNotThrow(() => storePasswordResetEmail(null, "Jake@Invalid"));
  assert.equal(storePasswordResetEmail(null, "Jake@Invalid"), "jake@invalid");
  assert.equal(resolvePasswordResetEmail("Query@Invalid", null), "query@invalid");
  assert.equal(resolvePasswordResetEmail(null, null), "");
  assert.doesNotThrow(() => clearPasswordResetEmail(null));

  assert.doesNotThrow(() => storePasswordResetEmail(storage, "Jake@Invalid"));
  assert.equal(resolvePasswordResetEmail("Query@Invalid", storage), "query@invalid");
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

test("active bids exclude recorded outcomes but keep pending final-stage packs", () => {
  const packs = [
    { id: "pending", stage: "final", outcome: null },
    { id: "won", outcome: "won" },
    { id: "lost", outcome: "lost" },
    { id: "withdrawn", outcome: "withdrawn" },
    { id: "legacy" },
  ];
  assert.deepEqual(activeBidPacks(packs).map((pack) => pack.id), ["pending", "legacy"]);
});

test("outcome payload validates lost reason and preserves zero value", () => {
  assert.equal(outcomeDraftIsValid("lost", "", "0"), false);
  for (const reason of LOSS_REASONS) {
    assert.equal(outcomeDraftIsValid("lost", reason, "0"), true);
  }
  assert.deepEqual(buildOutcomePayload("pending", "", ""), {
    outcome: null, reason: "", value: null,
  });
  assert.deepEqual(buildOutcomePayload("won", "price", "0"), {
    outcome: "won", reason: "", value: 0,
  });
  assert.deepEqual(buildOutcomePayload("lost", "price", "1250.50"), {
    outcome: "lost", reason: "price", value: 1250.5,
  });
  assert.equal(outcomeDraftIsValid("won", "", "-1"), false);
  assert.equal(outcomeDraftIsValid("won", "", "not-a-number"), false);
  assert.equal(outcomeDraftIsValid("won", "", "1000000000000001"), false);
});

test("next bid deadline ignores past and invalid dates and keeps a same-day date deadline", () => {
  const now = new Date(2025, 2, 14, 10, 0, 0);
  const packs = [
    { deadline: "2025-03-13" },
    { deadline: "not-a-date" },
    { deadline: null },
    { deadline: "2025-03-15" },
    { deadline: "2025-03-14" },
  ];

  assert.equal(nextBidDeadline(packs, now), "2025-03-14");
  assert.equal(nextBidDeadline([{ deadline: now.toISOString() }], now), null);
  assert.equal(nextBidDeadline([{ deadline: "invalid" }], now), null);
});

test("knowledge chunk count sums document chunks and returns zero for no valid chunks", () => {
  assert.equal(knowledgeChunkCount([{ chunks: 2 }, { chunks: 7 }, { chunks: 0 }]), 9);
  assert.equal(knowledgeChunkCount([]), 0);
  assert.equal(knowledgeChunkCount([{ chunks: Number.NaN }, { chunks: -3 }]), 0);
});

test("UI source pins reset copy, accessible metric tooltips and shared helper wiring", () => {
  const forgotSource = readFileSync(resolve(process.cwd(), "app/forgot-password/page.tsx"), "utf8");
  const resetSource = readFileSync(resolve(process.cwd(), "app/reset-password/page.tsx"), "utf8");
  const studioSource = readFileSync(resolve(process.cwd(), "app/studio/page.tsx"), "utf8");
  const landingSource = readFileSync(
    resolve(process.cwd(), "components/pre-sales/worker-landing.tsx"),
    "utf8",
  );
  const tooltipSource = readFileSync(
    resolve(process.cwd(), "components/pre-sales/metric-info-tooltip.tsx"),
    "utf8",
  );

  assert.doesNotMatch(forgotSource, /window\.sessionStorage/);
  assert.doesNotMatch(resetSource, /window\.sessionStorage/);
  assert.match(forgotSource, /getPasswordResetSessionStorage\(window\)/);
  assert.match(forgotSource, /storePasswordResetEmail\(storage, normalisedEmail\);[\s\S]*setLocation/);
  assert.match(resetSource, /resolvePasswordResetEmail\(queryEmail, storage\)/);
  assert.match(resetSource, /clearPasswordResetEmail\(storage\);[\s\S]*setSuccess\(true\)/);
  assert.ok(resetSource.includes(
    "We have sent a one-time code to the provided email address. Please check your email and enter the code below.",
  ));
  for (const source of [studioSource, landingSource]) {
    assert.ok(source.includes("aiDraftingPercent"));
    assert.ok(source.includes("AI_DRAFTING_DESCRIPTION"));
    assert.ok(source.includes("MetricInfoTooltip"));
    assert.ok(source.includes('label: "AI Drafting"'));
    assert.ok(source.includes("formatShortDate(nextBidDeadline(activePacks, Date.now()))"));
    assert.ok(source.includes("knowledgeChunkCount"));
    assert.ok(source.includes('label: "Data Volume"'));
    assert.ok(source.includes("`${dataVolume} chunks`"));
  }
  // Studio landing keeps a tenant-wide docs summary; the pre-sales worker landing is now scoped to
  // its own worker (agentId) so its knowledge stays its own (QIK-315 agent-scoped knowledge).
  assert.ok(studioSource.includes('queryKey: ["documents"], queryFn: () => listDocuments()'));
  assert.ok(landingSource.includes('queryKey: ["documents", agentId], queryFn: () => listDocuments(agentId)'));
  assert.match(tooltipSource, /Info/);
  assert.match(tooltipSource, /role="tooltip"/);
  assert.match(tooltipSource, /aria-describedby=/);
  assert.match(tooltipSource, /aria-label=/);
  assert.match(tooltipSource, /focus-visible:/);
  assert.match(tooltipSource, /stopPropagation/);
});

test("Creator worker usage and Studio calls use server contracts", () => {
  const apiSource = readFileSync(resolve(process.cwd(), "lib/api.ts"), "utf8");
  const dashboardSource = readFileSync(resolve(process.cwd(), "app/dashboard/page.tsx"), "utf8");
  const workersSource = readFileSync(resolve(process.cwd(), "app/workers/page.tsx"), "utf8");
  const studioSource = readFileSync(resolve(process.cwd(), "app/studio/[id]/page.tsx"), "utf8");
  const layoutSource = readFileSync(resolve(process.cwd(), "app/studio/[id]/layout.tsx"), "utf8");
  const guardSource = readFileSync(resolve(process.cwd(), "components/studio/worker-route-guard.tsx"), "utf8");
  const outcomeSource = readFileSync(resolve(process.cwd(), "components/pre-sales/outcome-dialog.tsx"), "utf8");
  const landingSource = readFileSync(resolve(process.cwd(), "components/pre-sales/worker-landing.tsx"), "utf8");

  assert.match(apiSource, /getAgentUsage/);
  assert.match(apiSource, /worker_limit/);
  assert.match(apiSource, /\.filter\(\(agent\) => agent\.enabled !== false\)/);
  assert.match(apiSource, /ask = \(conversation_id: string, question: string, agent_id: string\)/);
  assert.match(apiSource, /batchAnswer = \(questions: string\[\], agent_id: string\)/);
  assert.match(apiSource, /requestBlob/);
  assert.doesNotMatch(apiSource, /fetch\(`\$\{BASE\}\/agents\/batch-export/);
  for (const source of [dashboardSource, workersSource]) {
    assert.match(source, /getAgentUsage/);
    assert.doesNotMatch(source, /WORKER_LIMIT/);
    assert.match(source, /agent-usage/);
  }
  assert.match(layoutSource, /StudioWorkerRouteGuard/);
  assert.match(guardSource, /worker\.status !== "ready"/);
  assert.match(guardSource, /Worker unavailable/);
  assert.match(guardSource, /aria-live="assertive"/);
  assert.match(dashboardSource, /dashboard-worker-usage/);
  assert.match(dashboardSource, /aria-live=/);
  assert.match(workersSource, /workers-plan-usage/);
  assert.match(workersSource, /aria-live=/);
  assert.match(landingSource, /Edit outcome for/);
  assert.match(outcomeSource, /Update outcome for \{pack\.title\}/);
  assert.match(studioSource, /ask\(cid, question, agentId\)/);
  assert.match(studioSource, /batchAnswer\(questions, agentId\)/);
  assert.match(studioSource, /batchExportUrl\(questions, agentId\)/);
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
