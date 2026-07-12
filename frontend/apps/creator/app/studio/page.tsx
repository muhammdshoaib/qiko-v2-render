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
      <div className="flex min-h-screen flex-col bg-[#050810]">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-10 lg:px-12">
          <div className="mb-8 flex flex-col gap-4 sm:mb-10 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>Studio</h1>
              <p className="mt-1 text-[13px] text-slate-500">Your deployed workers, ready to manage and use</p>
            </div>
            <button onClick={() => router.push("/workers")}
              className="flex items-center gap-2 rounded-xl bg-indigo-500 px-4 py-2.5 text-[13px] font-semibold text-white shadow-lg shadow-indigo-500/15 transition-all hover:bg-indigo-400">
              <Plus className="size-4" /> Deploy Worker
            </button>
          </div>

          {agentsQ.isLoading && <p className="text-sm text-slate-400">Loading…</p>}

          {!agentsQ.isLoading && deployed.length === 0 && (
            <div className="py-16 text-center">
              <p className="mb-3 text-sm text-slate-400">No deployed workers yet — mark a worker ready in Creator first.</p>
              <Button variant="outline" onClick={() => router.push("/workers")}>Go to Workers</Button>
            </div>
          )}

          <div className="space-y-10">
            {groups.map(([category, items]) => (
              <section key={category}>
                <div className="mb-5">
                  <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{category}</h2>
                  <p className="mt-1 text-[12px] text-slate-500">Deployed and managed from here</p>
                </div>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  {items.map((a) => {
                    const idx = deployed.findIndex((d) => d.id === a.id);
                    const packs: RfpPack[] = packsQ[idx]?.data ?? [];
                    const activeBids = packs.length;
                    const inReview = packs.filter((p) => p.stage === "review" || p.stage === "final").length;
                    const avgReadiness = activeBids > 0 ? Math.round((inReview / activeBids) * 100) : 0;
                    const nextDeadline = packs.map((p) => p.deadline).filter(Boolean).sort()[0] ?? null;
                    return (
                      <button key={a.id} onClick={() => router.push(`/studio/${a.id}`)}
                        className="group w-full overflow-hidden rounded-2xl border border-white/[0.06] text-left transition-all duration-300 hover:border-indigo-500/30 hover:shadow-[0_0_60px_-15px_rgba(99,102,241,0.12)]"
                        style={{ background: "linear-gradient(165deg, rgba(255,255,255,0.024) 0%, rgba(255,255,255,0.004) 100%)" }}>
                        <div className="px-6 pt-6 pb-4">
                          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="flex items-center gap-3.5">
                              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.15)" }}>
                                <MessageSquare className="size-5 text-indigo-400" />
                              </span>
                              <div>
                                <h3 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{a.name}</h3>
                                <p className="mt-0.5 text-[11px] text-slate-500">{category.toLowerCase().replace(/\s+/g, "_")}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 self-start sm:self-auto">
                              <span className="flex items-center gap-1.5 rounded-full bg-emerald-400/[0.08] px-2.5 py-[3px] text-[9px] font-semibold uppercase tracking-wider text-emerald-400/80">
                                <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" /> Active
                              </span>
                              <ArrowRight className="size-4 text-slate-700 transition-colors group-hover:text-slate-400" />
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
                            {[
                              { label: "Active Bids", value: String(activeBids) },
                              { label: "Avg Readiness", value: activeBids > 0 ? `${avgReadiness}%` : "—" },
                              { label: "Data volume", value: `${dataVolume} chunks` },
                              { label: "Next Bid", value: nextDeadline ?? "—" },
                            ].map((m) => (
                              <div key={m.label} className="rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2.5">
                                <p className="text-[17px] font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>{m.value}</p>
                                <p className="mt-0.5 text-[9px] text-slate-500">{m.label}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
