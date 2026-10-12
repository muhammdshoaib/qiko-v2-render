"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function StudioPage() {
  return (
    <Suspense fallback={<div className="min-h-[50vh] bg-[#05070d]" aria-busy="true" />}>
      <RedirectToIntelligence />
    </Suspense>
  );
}

function RedirectToIntelligence() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const query = params.toString();
    router.replace(query ? `/studio/intelligence?${query}` : "/studio/intelligence");
  }, [params, router]);

  return <div className="min-h-[50vh] bg-[#05070d]" aria-busy="true" />;
}
