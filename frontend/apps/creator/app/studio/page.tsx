"use client";

import { useMemo } from "react";
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
    <AppShell title="Studio">
      <div className="min-h-screen bg-[#050810]">
        <StudioHome workers={workers} />
      </div>
    </AppShell>
  );
}
