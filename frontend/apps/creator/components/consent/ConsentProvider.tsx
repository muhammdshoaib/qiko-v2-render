"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  acceptAllConsent,
  createDefaultConsent,
  createPreferenceConsent,
  getConsentSignals,
  parseStoredConsent,
  readStoredConsent,
  rejectNonEssentialConsent,
  writeStoredConsent,
  CONSENT_STORAGE_KEY,
  CONSENT_SCHEMA_VERSION,
  CONSENT_POLICY_VERSION,
  TERMS_RELEASE_ID,
  PRIVACY_RELEASE_ID,
  COOKIES_RELEASE_ID,
  type ConsentRecord,
  type ConsentSignals,
} from "@/lib/consent/consent-record";
import { cleanupDeniedConsentResources } from "@/lib/consent/cleanup-registry";
import { getAuthenticatedConsent, recordAnonymousConsent, syncAuthenticatedConsent, type ServerConsent } from "@/lib/api";
import { ConsentBanner, ConsentPreferencesDialog, ConsentSettingsButton } from "./ConsentUI";

export const CONSENT_CHANGED_EVENT = "qiko:consent-changed";
const SERVER_CONSENT_EVENT = "qiko:server-consent";
let consentSyncQueue: Promise<void> = Promise.resolve();

type ConsentContextValue = {
  consent: ConsentRecord;
  hasDecision: boolean;
  preferencesOpen: boolean;
  openPreferences: () => void;
  closePreferences: () => void;
  acceptAll: () => void;
  rejectNonEssential: () => void;
  savePreferences: (choices: { preferences: boolean; analytics: boolean; marketing: boolean }) => void;
};

const ConsentContext = createContext<ConsentContextValue | null>(null);

function safeLocalStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function safeSessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function currentSignals(): ConsentSignals {
  if (typeof navigator === "undefined") return { gpc: false, dnt: false };
  return getConsentSignals(navigator as Navigator & { globalPrivacyControl?: boolean });
}

function serverConsentRecord(record: ServerConsent, signals: ConsentSignals): ConsentRecord | null {
  if (record.terms_release_id !== TERMS_RELEASE_ID || record.privacy_release_id !== PRIVACY_RELEASE_ID
      || record.cookies_release_id !== COOKIES_RELEASE_ID) return null;
  const decidedAt = new Date(record.created_at);
  if (!Number.isFinite(decidedAt.getTime())) return null;
  const expiresAt = new Date(decidedAt);
  expiresAt.setUTCFullYear(expiresAt.getUTCFullYear() + 1);
  if (expiresAt.getTime() <= Date.now()) return null;
  return {
    schemaVersion: CONSENT_SCHEMA_VERSION,
    decisionId: record.decision_id.replace(/^auth:/, ""),
    revision: record.client_revision,
    policyVersion: CONSENT_POLICY_VERSION,
    necessary: true,
    preferences: record.preferences,
    analytics: record.analytics,
    marketing: signals.gpc ? false : record.marketing,
    source: "preferences",
    decidedAt: decidedAt.toISOString(),
    updatedAt: decidedAt.toISOString(),
    expiresAt: expiresAt.toISOString(),
    signals,
  };
}

function safeGet(storage: Storage | null, key: string): string | null {
  try { return storage?.getItem(key) ?? null; } catch { return null; }
}

function safeSet(storage: Storage | null, key: string, value: string): void {
  try { storage?.setItem(key, value); } catch { return; }
}

function safeRemove(storage: Storage | null, key: string): void {
  try { storage?.removeItem(key); } catch { return; }
}

function anonymousConsentId(storage: Storage | null): string {
  const key = "qiko.consent.anonymous-id";
  const existing = safeGet(storage, key);
  if (existing) return existing;
  const value = crypto.randomUUID();
  safeSet(storage, key, value);
  return value;
}

function isCurrentDecision(record: ConsentRecord): boolean {
  return readStoredConsent(safeLocalStorage())?.decisionId === record.decisionId;
}

async function persistServerConsent(record: ConsentRecord): Promise<void> {
  const choices = { client_revision: record.revision,
    terms_release_id: TERMS_RELEASE_ID, privacy_release_id: PRIVACY_RELEASE_ID,
    cookies_release_id: COOKIES_RELEASE_ID, preferences: record.preferences,
    analytics: record.analytics, marketing: record.marketing };
  const sync = await syncAuthenticatedConsent({ ...choices, decision_id: `auth:${record.decisionId}` });
  if (sync === "stale") {
    const latest = await getAuthenticatedConsent();
    if (typeof latest === "object") window.dispatchEvent(new CustomEvent<ServerConsent>(SERVER_CONSENT_EVENT, { detail: latest }));
    return;
  }
  if (sync === "user") { if (isCurrentDecision(record)) safeRemove(safeLocalStorage(), "qiko.consent.pending-sync"); return; }
  if (sync === "anonymous") {
    try {
      await recordAnonymousConsent({ ...choices, decision_id: `anon:${record.decisionId}`,
        anonymous_id: anonymousConsentId(safeLocalStorage()) });
      if (isCurrentDecision(record)) safeRemove(safeLocalStorage(), "qiko.consent.pending-sync");
      return;
    } catch {
      if (isCurrentDecision(record)) safeSet(safeLocalStorage(), "qiko.consent.pending-sync", JSON.stringify(record));
      return;
    }
  }
  if (isCurrentDecision(record)) safeSet(safeLocalStorage(), "qiko.consent.pending-sync", JSON.stringify(record));
}

function deleteRegisteredCookie(name: string): void {
  document.cookie = `${encodeURIComponent(name)}=; Max-Age=0; Path=/; SameSite=Lax`;
}

export function ConsentProvider({ children }: { children: ReactNode }) {
  const [consent, setConsent] = useState<ConsentRecord>(() =>
    createDefaultConsent({ gpc: false, dnt: false }),
  );
  const [hasDecision, setHasDecision] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);

  const applyRecord = useCallback((record: ConsentRecord, persist: boolean) => {
    const stored = persist ? readStoredConsent(safeLocalStorage()) : null;
    const now = new Date().toISOString();
    const effective = stored && record.revision <= stored.revision
      ? { ...record, revision: stored.revision + 1, updatedAt: now }
      : record;
    setConsent(effective);
    setHasDecision(effective.source !== "default");
    if (persist) {
      writeStoredConsent(safeLocalStorage(), effective);
      safeSet(safeLocalStorage(), "qiko.consent.pending-sync", JSON.stringify(effective));
      const sync = () => persistServerConsent(effective);
      consentSyncQueue = consentSyncQueue.then(sync, sync);
    }
    cleanupDeniedConsentResources(effective, {
      localStorage: safeLocalStorage(),
      sessionStorage: safeSessionStorage(),
      deleteCookie: deleteRegisteredCookie,
    });
    window.dispatchEvent(new CustomEvent<ConsentRecord>(CONSENT_CHANGED_EVENT, { detail: effective }));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const resolveConsent = async () => {
      const storage = safeLocalStorage();
      const signals = currentSignals();
      const server = await getAuthenticatedConsent();
      if (cancelled) return;
      if (typeof server === "object") {
        const authoritative = serverConsentRecord(server, signals);
        if (!authoritative) {
          safeRemove(storage, CONSENT_STORAGE_KEY);
          safeRemove(storage, "qiko.consent.pending-sync");
          applyRecord(createDefaultConsent(signals), false);
          return;
        }
        if (signals.gpc && server.marketing) {
          applyRecord(createPreferenceConsent({
            preferences: authoritative.preferences,
            analytics: authoritative.analytics,
            marketing: false,
          }, signals), true);
          return;
        }
        writeStoredConsent(storage, authoritative);
        safeRemove(storage, "qiko.consent.pending-sync");
        applyRecord(authoritative, false);
        return;
      }
      const stored = readStoredConsent(storage);
      if (!stored || server === "retry") {
        applyRecord(createDefaultConsent(signals), false);
        return;
      }
      if (signals.gpc && stored.marketing) {
        applyRecord(createPreferenceConsent(
          { preferences: stored.preferences, analytics: stored.analytics, marketing: false }, signals), true);
        return;
      }
      const reconciled = { ...stored, signals: { gpc: signals.gpc, dnt: signals.dnt } };
      applyRecord(reconciled, false);
      const sync = () => persistServerConsent(reconciled);
      consentSyncQueue = consentSyncQueue.then(sync, sync);
    };
    void resolveConsent();
    return () => { cancelled = true; };
  }, [applyRecord]);

  useEffect(() => {
    const raw = safeGet(safeLocalStorage(), "qiko.consent.pending-sync");
    if (!raw) return;
    const pending = parseStoredConsent(raw);
    if (pending) {
      const sync = () => persistServerConsent(pending);
      consentSyncQueue = consentSyncQueue.then(sync, sync);
    } else safeRemove(safeLocalStorage(), "qiko.consent.pending-sync");
  }, []);

  useEffect(() => {
    const onServerConsent = (event: Event) => {
      const record = serverConsentRecord((event as CustomEvent<ServerConsent>).detail, currentSignals());
      if (!record) {
        applyRecord(createDefaultConsent(currentSignals()), false);
        return;
      }
      writeStoredConsent(safeLocalStorage(), record);
      safeRemove(safeLocalStorage(), "qiko.consent.pending-sync");
      applyRecord(record, false);
    };
    window.addEventListener(SERVER_CONSENT_EVENT, onServerConsent);
    return () => window.removeEventListener(SERVER_CONSENT_EVENT, onServerConsent);
  }, [applyRecord]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== CONSENT_STORAGE_KEY) return;
      const signals = currentSignals();
      const parsed = parseStoredConsent(event.newValue);
      if (!parsed) {
        const denied = createDefaultConsent(signals);
        setConsent(denied);
        setHasDecision(false);
        cleanupDeniedConsentResources(denied, {
          localStorage: safeLocalStorage(),
          sessionStorage: safeSessionStorage(),
          deleteCookie: deleteRegisteredCookie,
        });
        window.dispatchEvent(new CustomEvent<ConsentRecord>(CONSENT_CHANGED_EVENT, { detail: denied }));
        return;
      }
      const synced = signals.gpc && parsed.marketing
        ? createPreferenceConsent({ preferences: parsed.preferences, analytics: parsed.analytics, marketing: false }, signals)
        : { ...parsed, signals };
      setConsent(synced);
      setHasDecision(true);
      if (synced.decisionId !== parsed.decisionId) writeStoredConsent(safeLocalStorage(), synced);
      safeSet(safeLocalStorage(), "qiko.consent.pending-sync", JSON.stringify(synced));
      const sync = () => persistServerConsent(synced);
      consentSyncQueue = consentSyncQueue.then(sync, sync);
      cleanupDeniedConsentResources(synced, {
        localStorage: safeLocalStorage(),
        sessionStorage: safeSessionStorage(),
        deleteCookie: deleteRegisteredCookie,
      });
      window.dispatchEvent(new CustomEvent<ConsentRecord>(CONSENT_CHANGED_EVENT, { detail: synced }));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const acceptAll = useCallback(() => {
    applyRecord(acceptAllConsent(currentSignals()), true);
    setPreferencesOpen(false);
  }, [applyRecord]);

  const rejectNonEssential = useCallback(() => {
    applyRecord(rejectNonEssentialConsent(currentSignals()), true);
    setPreferencesOpen(false);
  }, [applyRecord]);

  const savePreferences = useCallback((choices: { preferences: boolean; analytics: boolean; marketing: boolean }) => {
    applyRecord(createPreferenceConsent(choices, currentSignals()), true);
    setPreferencesOpen(false);
  }, [applyRecord]);

  const value = useMemo<ConsentContextValue>(() => ({
    consent,
    hasDecision,
    preferencesOpen,
    openPreferences: () => setPreferencesOpen(true),
    closePreferences: () => setPreferencesOpen(false),
    acceptAll,
    rejectNonEssential,
    savePreferences,
  }), [acceptAll, consent, hasDecision, preferencesOpen, rejectNonEssential, savePreferences]);

  return (
    <ConsentContext.Provider value={value}>
      {children}
      {!hasDecision ? <ConsentBanner /> : null}
      <ConsentPreferencesDialog />
      <ConsentSettingsButton variant="floating" />
    </ConsentContext.Provider>
  );
}

export function useConsent(): ConsentContextValue {
  const context = useContext(ConsentContext);
  if (!context) throw new Error("useConsent must be used within ConsentProvider");
  return context;
}
