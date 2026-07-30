import type { ConsentRecord, ConsentStorage } from "./consent-record";
import { CONSENT_STORAGE_KEY } from "./consent-record";

export type NonEssentialConsentCategory = "analytics" | "marketing";
export type ConsentResource = {
  category: NonEssentialConsentCategory;
  kind: "cookie" | "localStorage" | "sessionStorage";
  name: string;
};

type CleanupEnvironment = {
  localStorage?: ConsentStorage | null;
  sessionStorage?: ConsentStorage | null;
  deleteCookie?: (name: string) => void;
};

const resources = new Map<string, ConsentResource>();
const PROTECTED_NAMES = new Set([
  CONSENT_STORAGE_KEY,
  "qiko_access",
  "qiko_refresh",
  "qiko_csrf",
  "qiko.password-reset.email",
  "__cf_bm",
  "cf_clearance",
]);

export function registerConsentResource(resource: ConsentResource): () => void {
  if (!resource.name.trim() || PROTECTED_NAMES.has(resource.name)) return () => undefined;
  const key = `${resource.category}:${resource.kind}:${resource.name}`;
  resources.set(key, resource);
  return () => resources.delete(key);
}

export function clearConsentResourceRegistry(): void {
  resources.clear();
}

function removeStorageItem(storage: ConsentStorage | null | undefined, name: string): void {
  try {
    storage?.removeItem(name);
  } catch {
    // Storage may be blocked by the browser. Cleanup remains best effort.
  }
}

export function cleanupDeniedConsentResources(
  consent: ConsentRecord,
  environment: CleanupEnvironment,
): void {
  for (const resource of resources.values()) {
    if (consent[resource.category]) continue;

    if (resource.kind === "cookie") {
      try {
        environment.deleteCookie?.(resource.name);
      } catch {
        // Cookie cleanup remains best effort.
      }
    } else if (resource.kind === "localStorage") {
      removeStorageItem(environment.localStorage, resource.name);
    } else {
      removeStorageItem(environment.sessionStorage, resource.name);
    }
  }
}
