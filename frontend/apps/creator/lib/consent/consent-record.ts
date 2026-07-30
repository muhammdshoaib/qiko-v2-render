export const CONSENT_STORAGE_KEY = "qiko.consent.v1";
export const CONSENT_SCHEMA_VERSION = 1 as const;
export const CONSENT_POLICY_VERSION = "2026-07-24";
export const TERMS_RELEASE_ID = "terms-2026-07-24";
export const PRIVACY_RELEASE_ID = "privacy-2026-07-24";
export const COOKIES_RELEASE_ID = "cookies-2026-07-24";

export type ConsentSource = "default" | "banner" | "preferences" | "gpc" | "dnt";
export type ConsentSignals = { gpc: boolean; dnt: boolean };

export type ConsentRecord = {
  schemaVersion: typeof CONSENT_SCHEMA_VERSION;
  decisionId: string;
  revision: number;
  policyVersion: typeof CONSENT_POLICY_VERSION;
  necessary: true;
  preferences: boolean;
  analytics: boolean;
  marketing: boolean;
  source: ConsentSource;
  decidedAt: string;
  updatedAt: string;
  expiresAt: string;
  signals: ConsentSignals;
};

export type ConsentStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const SOURCES = new Set<ConsentSource>(["default", "banner", "preferences", "gpc", "dnt"]);

function expiresInTwelveMonths(now: Date): string {
  const expiry = new Date(now.getTime());
  expiry.setUTCFullYear(expiry.getUTCFullYear() + 1);
  return expiry.toISOString();
}

function makeConsent(
  choices: { preferences: boolean; analytics: boolean; marketing: boolean },
  signals: ConsentSignals,
  source: ConsentSource,
  now: Date,
): ConsentRecord {
  const timestamp = now.toISOString();
  return {
    schemaVersion: CONSENT_SCHEMA_VERSION,
    decisionId: globalThis.crypto?.randomUUID?.() ?? `${timestamp}-${Math.random()}`,
    revision: now.getTime(),
    policyVersion: CONSENT_POLICY_VERSION,
    necessary: true,
    preferences: choices.preferences,
    analytics: choices.analytics,
    marketing: signals.gpc ? false : choices.marketing,
    source,
    decidedAt: timestamp,
    updatedAt: timestamp,
    expiresAt: expiresInTwelveMonths(now),
    signals: { ...signals },
  };
}

export function createDefaultConsent(signals: ConsentSignals, now = new Date()): ConsentRecord {
  return makeConsent({ preferences: false, analytics: false, marketing: false }, signals, "default", now);
}

export function acceptAllConsent(signals: ConsentSignals, now = new Date()): ConsentRecord {
  return makeConsent({ preferences: true, analytics: true, marketing: true }, signals, signals.gpc ? "gpc" : "banner", now);
}

export function rejectNonEssentialConsent(signals: ConsentSignals, now = new Date()): ConsentRecord {
  return makeConsent(
    { preferences: false, analytics: false, marketing: false },
    signals,
    signals.gpc ? "gpc" : signals.dnt ? "dnt" : "banner",
    now,
  );
}

export function createPreferenceConsent(
  choices: { preferences: boolean; analytics: boolean; marketing: boolean },
  signals: ConsentSignals,
  now = new Date(),
): ConsentRecord {
  return makeConsent(choices, signals, signals.gpc ? "gpc" : "preferences", now);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

export function parseStoredConsent(raw: string | null, now = new Date()): ConsentRecord | null {
  if (!raw) return null;

  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const record = value as Partial<ConsentRecord>;

    if (
      record.schemaVersion !== CONSENT_SCHEMA_VERSION ||
      typeof record.decisionId !== "string" || record.decisionId.length < 8 ||
      typeof record.revision !== "number" || !Number.isSafeInteger(record.revision) ||
      record.policyVersion !== CONSENT_POLICY_VERSION ||
      record.necessary !== true ||
      typeof record.preferences !== "boolean" ||
      typeof record.analytics !== "boolean" ||
      typeof record.marketing !== "boolean" ||
      typeof record.source !== "string" ||
      !SOURCES.has(record.source as ConsentSource) ||
      !isIsoDate(record.decidedAt) ||
      !isIsoDate(record.updatedAt) ||
      !isIsoDate(record.expiresAt) ||
      !record.signals ||
      typeof record.signals.gpc !== "boolean" ||
      typeof record.signals.dnt !== "boolean" ||
      Date.parse(record.expiresAt) <= now.getTime()
    ) {
      return null;
    }

    if (
      (record.signals.gpc && record.marketing) ||
      Date.parse(record.decidedAt) > Date.parse(record.updatedAt) ||
      expiresInTwelveMonths(new Date(record.updatedAt)) !== record.expiresAt
    ) {
      return null;
    }
    return record as ConsentRecord;
  } catch {
    return null;
  }
}

export function readStoredConsent(storage: ConsentStorage | null, now = new Date()): ConsentRecord | null {
  if (!storage) return null;
  try {
    return parseStoredConsent(storage.getItem(CONSENT_STORAGE_KEY), now);
  } catch {
    return null;
  }
}

export function writeStoredConsent(storage: ConsentStorage | null, record: ConsentRecord): boolean {
  if (!storage) return false;
  try {
    storage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(record));
    return true;
  } catch {
    return false;
  }
}

export function getConsentSignals(navigatorLike?: {
  globalPrivacyControl?: boolean;
  doNotTrack?: string | null;
} | null): ConsentSignals {
  const dnt = navigatorLike?.doNotTrack?.toLowerCase();
  return {
    gpc: navigatorLike?.globalPrivacyControl === true,
    dnt: dnt === "1" || dnt === "yes",
  };
}
