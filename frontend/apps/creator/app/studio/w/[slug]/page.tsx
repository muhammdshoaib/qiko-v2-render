"use client";

import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/app-shell";
import { WorkerProfile } from "@/components/studio/worker-profile";
import { listAgents } from "@/lib/api";
import { SHOWCASE_WORKERS, attachLiveWorkers, workerBySlug } from "@/lib/studio/showcase";

export default function StudioWorkerProfilePage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: listAgents, retry: false });
  const worker = useMemo(() => {
    const live = attachLiveWorkers(SHOWCASE_WORKERS, agentsQ.data ?? []);
    return live.find((item) => item.slug === slug) ?? workerBySlug(slug);
  }, [agentsQ.data, slug]);

  if (!agentsQ.isLoading && !worker) {
    router.replace("/studio");
    return null;
  }

  return (
    <AppShell title={worker?.name ?? "Worker"}>
      <div className="min-h-screen bg-background">
        {worker ? <WorkerProfile worker={worker} /> : <p className="px-6 py-10 text-sm text-slate-400">Loading worker…</p>}
      </div>
    </AppShell>
  );
}
