"use client";

import { Suspense, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/app-shell";
import { StudioHome } from "@/components/studio/studio-home";
import { listAgents } from "@/lib/api";
import { SHOWCASE_WORKERS, attachLiveWorkers } from "@/lib/studio/showcase";

export default function StudioPage() {
  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: listAgents, retry: false });
  const workers = useMemo(
    () => attachLiveWorkers(SHOWCASE_WORKERS, agentsQ.data ?? []),
    [agentsQ.data],
  );

  return (
    <AppShell title="Pulse">
      <Suspense fallback={<div className="min-h-[50vh] bg-[#F2F4FB]" aria-busy="true" />}>
        <StudioHome workers={workers} />
      </Suspense>
    </AppShell>
  );
}
