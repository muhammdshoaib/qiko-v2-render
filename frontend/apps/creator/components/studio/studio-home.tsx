"use client";

import { useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PulseApp } from "@/components/pulse/pulse-app";
import { mergeNav, parsePulseNav, writePulseQuery, type PulseNav } from "@/components/pulse/route";
import type { ShowcaseWorker } from "@/lib/studio/showcase";

export function StudioHome({ workers }: { workers: ShowcaseWorker[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const nav = parsePulseNav(params);

  const onNav = useCallback((next: Partial<PulseNav>) => {
    const query = writePulseQuery(mergeNav(nav, next), params);
    const suffix = query.toString();
    router.replace(suffix ? `/studio?${suffix}` : "/studio", { scroll: false });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [nav, params, router]);

  return <PulseApp workers={workers} nav={nav} onNav={onNav} />;
}
