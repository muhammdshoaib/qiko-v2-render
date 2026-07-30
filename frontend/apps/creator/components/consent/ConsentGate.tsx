"use client";

import { useEffect, useId, type ReactNode } from "react";
import type { NonEssentialConsentCategory } from "@/lib/consent/cleanup-registry";
import { useConsent } from "./ConsentProvider";

export function ConsentGate({
  category,
  children,
  fallback = null,
}: {
  category: NonEssentialConsentCategory;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { consent } = useConsent();
  return consent[category] ? children : fallback;
}

export function ConsentScript({
  category,
  src,
  id,
  async = true,
  defer,
  integrity,
  crossOrigin,
  referrerPolicy = "no-referrer",
}: {
  category: NonEssentialConsentCategory;
  src: string;
  id?: string;
  async?: boolean;
  defer?: boolean;
  integrity?: string;
  crossOrigin?: "anonymous" | "use-credentials";
  referrerPolicy?: ReferrerPolicy;
}) {
  const generatedId = useId();
  const scriptId = id ?? `qiko-consent-script-${generatedId.replace(/:/g, "")}`;
  const { consent } = useConsent();

  useEffect(() => {
    if (!consent[category] || document.getElementById(scriptId)) return;

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = src;
    script.async = async;
    script.defer = defer ?? false;
    script.referrerPolicy = referrerPolicy;
    if (integrity) script.integrity = integrity;
    if (crossOrigin) script.crossOrigin = crossOrigin;
    document.head.appendChild(script);

    return () => script.remove();
  }, [async, category, consent, crossOrigin, defer, integrity, referrerPolicy, scriptId, src]);

  return null;
}
