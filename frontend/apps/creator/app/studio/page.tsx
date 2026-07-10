"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowRight, MessageSquare, Plus } from "lucide-react";
import { Button } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { listAgents, listDocuments, listRfpPacks, type Agent, type RfpPack } from "@/lib/api";

function workerCategory(a: Agent): string {
  const expertise = a.config?.expertise as string | undefined;
  return expertise?.trim() || "General";
}

export default function StudioPage() {
  const router = useRouter();
  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const workers = agentsQ.data ?? [];

  // "Deployed" here means live/ready -- Creator is where workers are built and trained,
  // Studio is where the deployed ones are operated day to day.
  const deployed = useMemo(() => workers.filter((a) => a.status === "ready"), [workers]);

  const packsQ = useQueries({
    queries: deployed.map((a) => ({
      queryKey: ["rfp-packs", a.id],
      queryFn: () => listRfpPacks(a.id),
    })),
  });
  const docsQ = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const dataVolume = docsQ.data?.reduce((n, d) => n + d.chunks, 0) ?? 0;

  const groups = useMemo(() => {
    const byCategory = new Map<string, Agent[]>();
    for (const a of deployed) {
      const key = workerCategory(a);
      byCategory.set(key, [...(byCategory.get(key) ?? []), a]);
    }
    return Array.from(byCategory.entries());
  }, [deployed]);

  return (
    <AppShell title="Studio">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Studio</h1>
          <p className="text-sm text-muted-foreground">Your deployed workers, ready to manage and use</p>
        </div>
        <Button onClick={() => router.push("/workers")}>
          <Plus className="size-4" /> Deploy Worker
        </Button>
      </div>

      {agentsQ.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!agentsQ.isLoading && deployed.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-sm text-muted-foreground mb-3">No deployed workers yet — mark a worker ready in Creator first.</p>
          <Button variant="outline" onClick={() => router.push("/workers")}>Go to Workers</Button>
        </div>
      )}

      <div className="space-y-8">
        {groups.map(([category, items]) => (
          <div key={category}>
            <h2 className="text-sm font-semibold mb-1">{category}</h2>
            <p className="text-xs text-muted-foreground mb-3">Deployed and managed from here</p>
            <div className="space-y-3">
              {items.map((a) => {
                const idx = deployed.findIndex((d) => d.id === a.id);
                const packs: RfpPack[] = packsQ[idx]?.data ?? [];
                const activeBids = packs.length;
                const inReview = packs.filter((p) => p.stage === "review" || p.stage === "final").length;
                const avgReadiness = activeBids > 0 ? Math.round((inReview / activeBids) * 100) : 0;
                const nextDeadline = packs.map((p) => p.deadline).filter(Boolean).sort()[0] ?? null;
                return (
                  <button key={a.id} onClick={() => router.push(`/studio/${a.id}`)}
                    className="block w-full rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/40">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                          <MessageSquare className="size-4" />
                        </span>
                        <div>
                          <p className="text-sm font-semibold">{a.name}</p>
                          <p className="text-xs text-muted-foreground">{category.toLowerCase().replace(/\s+/g, "_")}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">Active</span>
                        <ArrowRight className="size-4 text-muted-foreground" />
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-border/60 pt-4">
                      <div>
                        <p className="text-lg font-semibold">{activeBids}</p>
                        <p className="text-xs text-muted-foreground">Active Bids</p>
                      </div>
                      <div>
                        <p className="text-lg font-semibold">{activeBids > 0 ? `${avgReadiness}%` : "—"}</p>
                        <p className="text-xs text-muted-foreground">Avg Readiness</p>
                      </div>
                      <div>
                        <p className="text-lg font-semibold">{dataVolume} chunks</p>
                        <p className="text-xs text-muted-foreground">Data volume</p>
                      </div>
                      <div>
                        <p className="text-lg font-semibold">{nextDeadline ?? "—"}</p>
                        <p className="text-xs text-muted-foreground">Next Bid</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
