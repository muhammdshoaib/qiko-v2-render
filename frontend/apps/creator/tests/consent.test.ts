import assert from "node:assert/strict";
import test from "node:test";

import {
  CONSENT_POLICY_VERSION,
  CONSENT_SCHEMA_VERSION,
  CONSENT_STORAGE_KEY,
  acceptAllConsent,
  createDefaultConsent,
  createPreferenceConsent,
  parseStoredConsent,
  readStoredConsent,
  rejectNonEssentialConsent,
  writeStoredConsent,
} from "../lib/consent/consent-record";
import {
  clearConsentResourceRegistry,
  cleanupDeniedConsentResources,
  registerConsentResource,
} from "../lib/consent/cleanup-registry";

class MemoryStorage {
  readonly values = new Map<string, string>();

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
  getItem(): string | null { throw new Error("blocked"); }
  setItem(): void { throw new Error("blocked"); }
  removeItem(): void { throw new Error("blocked"); }
}

const NOW = new Date("2026-07-24T12:00:00.000Z");

function validStoredRecord(): string {
  return JSON.stringify(createPreferenceConsent(
    { preferences: true, analytics: true, marketing: false },
    { gpc: false, dnt: false },
    NOW,
  ));
}

test("consent defaults to deny during SSR and records detected privacy signals", () => {
  const consent = createDefaultConsent({ gpc: true, dnt: true }, NOW);

  assert.equal(CONSENT_STORAGE_KEY, "qiko.consent.v1");
  assert.equal(consent.schemaVersion, CONSENT_SCHEMA_VERSION);
  assert.equal(consent.policyVersion, CONSENT_POLICY_VERSION);
  assert.equal(consent.necessary, true);
  assert.equal(consent.analytics, false);
  assert.equal(consent.marketing, false);
  assert.equal(consent.source, "default");
  assert.deepEqual(consent.signals, { gpc: true, dnt: true });
});

test("stored consent validates its complete schema", () => {
  const parsed = parseStoredConsent(validStoredRecord(), NOW);
  assert.equal(parsed?.analytics, true);

  const malformed = JSON.stringify({ ...JSON.parse(validStoredRecord()), necessary: false });
  assert.equal(parseStoredConsent(malformed, NOW), null);
  assert.equal(parseStoredConsent("not-json", NOW), null);
  assert.equal(parseStoredConsent(null, NOW), null);
});

test("consent storage access is safe when browser storage is blocked", () => {
  const storage = new ThrowingStorage();
  assert.equal(readStoredConsent(storage, NOW), null);
  assert.equal(writeStoredConsent(storage, createDefaultConsent({ gpc: false, dnt: false }, NOW)), false);
});

test("expired consent and policy or schema mismatches re-prompt with default deny", () => {
  const record = JSON.parse(validStoredRecord());

  assert.equal(parseStoredConsent(JSON.stringify(record), new Date("2027-07-25T12:00:00.000Z")), null);
  assert.equal(parseStoredConsent(JSON.stringify({ ...record, policyVersion: "older" }), NOW), null);
  assert.equal(parseStoredConsent(JSON.stringify({ ...record, schemaVersion: 99 }), NOW), null);
  assert.equal(parseStoredConsent(JSON.stringify({ ...record, expiresAt: "2099-01-01T00:00:00.000Z" }), NOW), null);
});

test("accept, reject and preference decisions have a 12-month logical expiry", () => {
  const accepted = acceptAllConsent({ gpc: false, dnt: false }, NOW);
  assert.equal(accepted.analytics, true);
  assert.equal(accepted.marketing, true);
  assert.equal(accepted.source, "banner");
  assert.equal(accepted.expiresAt, "2027-07-24T12:00:00.000Z");

  const rejected = rejectNonEssentialConsent({ gpc: false, dnt: true }, NOW);
  assert.equal(rejected.analytics, false);
  assert.equal(rejected.marketing, false);
  assert.equal(rejected.source, "dnt");

  const preferences = createPreferenceConsent(
    { preferences: true, analytics: true, marketing: true },
    { gpc: false, dnt: true },
    NOW,
  );
  assert.equal(preferences.analytics, true);
  assert.equal(preferences.marketing, true, "DNT is an overridable default");
  assert.equal(preferences.source, "preferences");
});

test("GPC conservatively locks marketing off for every decision", () => {
  const signals = { gpc: true, dnt: false };
  assert.equal(acceptAllConsent(signals, NOW).marketing, false);
  assert.equal(createPreferenceConsent({ preferences: true, analytics: true, marketing: true }, signals, NOW).marketing, false);
});

test("cleanup removes only registered denied-category resources and protects necessary state", () => {
  clearConsentResourceRegistry();
  const localStorage = new MemoryStorage();
  const sessionStorage = new MemoryStorage();
  localStorage.setItem("analytics.client", "1");
  localStorage.setItem(CONSENT_STORAGE_KEY, validStoredRecord());
  localStorage.setItem("unregistered", "keep");
  sessionStorage.setItem("marketing.draft", "1");
  sessionStorage.setItem("qiko.password-reset.email", "person" + "@" + "example.com");

  registerConsentResource({ category: "analytics", kind: "localStorage", name: "analytics.client" });
  registerConsentResource({ category: "marketing", kind: "sessionStorage", name: "marketing.draft" });
  registerConsentResource({ category: "marketing", kind: "localStorage", name: CONSENT_STORAGE_KEY });
  registerConsentResource({ category: "marketing", kind: "sessionStorage", name: "qiko.password-reset.email" });
  registerConsentResource({ category: "analytics", kind: "cookie", name: "analytics_id" });
  registerConsentResource({ category: "marketing", kind: "cookie", name: "qiko_access" });
  registerConsentResource({ category: "marketing", kind: "cookie", name: "__cf_bm" });

  const deletedCookies: string[] = [];
  cleanupDeniedConsentResources(
    rejectNonEssentialConsent({ gpc: false, dnt: false }, NOW),
    { localStorage, sessionStorage, deleteCookie: (name) => deletedCookies.push(name) },
  );

  assert.equal(localStorage.getItem("analytics.client"), null);
  assert.equal(sessionStorage.getItem("marketing.draft"), null);
  assert.equal(localStorage.getItem(CONSENT_STORAGE_KEY) !== null, true);
  assert.equal(sessionStorage.getItem("qiko.password-reset.email"), "person" + "@" + "example.com");
  assert.equal(localStorage.getItem("unregistered"), "keep");
  assert.deepEqual(deletedCookies, ["analytics_id"]);
});
