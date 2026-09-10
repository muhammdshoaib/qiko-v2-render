import type { Page } from "@playwright/test";

/** Pre-seed a consent decision so the cookie banner never mounts.
 *
 *  Clicking the banner away is inherently racy: it mounts asynchronously after a consent probe, so a
 *  `count()` check or even a bounded `waitFor` can miss it, and once mounted it OVERLAYS whatever is
 *  underneath, making every subsequent click time out. Writing a valid decision before any page
 *  script runs removes the banner from the equation entirely.
 *
 *  Shape mirrors apps/creator/lib/consent/consent-record.ts (schemaVersion 1, policy 2026-07-24).
 *
 *  Extracted here because it was about to exist a third time. `critical-path-auth.spec.ts` had this
 *  exact function inline, `finance-drilldown.spec.ts` stubs the consent endpoint instead, and
 *  `pre-sales-outcome.spec.ts` had neither, which is why its tablet/mobile case failed: the banner
 *  intercepted the pointer event on the outcome button. Divergent copies of a test affordance drift,
 *  and the drift is invisible while the suite runs nowhere (QIKO-1091).
 *
 *  Note this masks a REAL defect rather than fixing it: at narrow widths the banner genuinely
 *  obstructs controls underneath it. That is tracked as QIKO-1090. A test whose subject is dialog
 *  responsiveness should not also be the only thing failing because of it.
 */
export async function seedConsent(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const now = new Date();
    const expires = new Date(now.getTime());
    expires.setUTCFullYear(expires.getUTCFullYear() + 1);
    const timestamp = now.toISOString();
    const record = {
      schemaVersion: 1,
      decisionId: `e2e-${timestamp}`,
      revision: now.getTime(),
      policyVersion: "2026-07-24",
      necessary: true,
      preferences: false,
      analytics: false,
      marketing: false,
      source: "banner",
      decidedAt: timestamp,
      updatedAt: timestamp,
      expiresAt: expires.toISOString(),
      signals: { gpc: false, dnt: false },
    };
    try {
      window.localStorage.setItem("qiko.consent.v1", JSON.stringify(record));
    } catch {
      // Storage disabled in this context; the caller's banner assertions simply do not apply.
    }
  });
}
