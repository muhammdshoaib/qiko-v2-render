"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Target } from "lucide-react";
import { Badge, Button } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { createAgent, listAgents, type Agent } from "@/lib/api";

const WORKER_LIMIT = 3;

function workerCategory(a: Agent): string {
  const expertise = a.config?.expertise as string | undefined;
  return expertise?.trim() || "General";
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", { month: "long", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

export default function WorkersPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const workers = agents.data ?? [];
  const atLimit = workers.length >= WORKER_LIMIT;

  const create = useMutation({
    mutationFn: () => createAgent(name),
    onSuccess: () => { setName(""); qc.invalidateQueries({ queryKey: ["agents"] }); },
  });

  const groups = useMemo(() => {
    const byCategory = new Map<string, Agent[]>();
    for (const a of workers) {
      const key = workerCategory(a);
      byCategory.set(key, [...(byCategory.get(key) ?? []), a]);
    }
    return Array.from(byCategory.entries());
  }, [workers]);

  return (
    <AppShell title="Workers">
      <div className="relative flex flex-col gap-4 border-b border-white/5 bg-[#0a0f1a]/80 px-4 py-4 backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-6">
        <div>
          <h1 className="mb-1 text-2xl font-bold" style={{
            fontFamily: "var(--font-display)",
            background: "linear-gradient(135deg, #fff 0%, #6366F1 50%, #22D3EE 100%)",
            WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent",
          }}>
            Your Workers
          </h1>
          <p className="text-sm text-slate-400">{workers.length} active worker{workers.length === 1 ? "" : "s"}</p>
        </div>
        <div className="flex w-full items-center justify-start gap-3 sm:w-auto sm:justify-end">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New worker name..."
            className="w-56 rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          <Button disabled={atLimit || !name || create.isPending} onClick={() => create.mutate()}
            className="rounded-xl bg-gradient-to-r from-[#6366F1] to-[#22D3EE] font-medium text-white shadow-lg shadow-[#6366F1]/20 hover:opacity-90">
            <Plus className="size-4" /> Create Worker
          </Button>
        </div>
      </div>

      <div className="p-4 sm:p-6 lg:p-8">
        {create.isError && <p className="mb-4 text-sm text-destructive">Plan limit reached or not permitted.</p>}
        {agents.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

        {!agents.isLoading && workers.length === 0 && (
          <div className="py-16 text-center">
            <p className="text-sm text-muted-foreground mb-3">No workers yet — build your first AI expert.</p>
          </div>
        )}

        <div className="mx-auto max-w-6xl space-y-8 sm:space-y-10">
          {groups.map(([category, items]) => (
            <div key={category}>
              <div className="mb-4 flex items-center gap-3">
                <span className="flex size-10 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10">
                  <Target className="size-5 text-cyan-400" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold text-white">{category}</h2>
                  <p className="text-xs text-slate-500">{items.length} worker{items.length === 1 ? "" : "s"}</p>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                {items.map((a) => (
                  <WorkerCard key={a.id} agent={a} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}

function WorkerCard({ agent }: { agent: Agent }) {
  return (
    <Link href={`/workers/${agent.id}`} className="group cursor-pointer block">
      <div className="relative overflow-hidden rounded-xl border border-white/10 bg-[#0a0f1a]/80 py-2 backdrop-blur-xl">
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cyan-500 to-purple-500" />
        <div className="flex items-start gap-4 p-5">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-500 text-xl font-bold text-white shadow-lg transition-shadow group-hover:shadow-xl">
            {agent.name.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-semibold text-white capitalize transition-colors group-hover:text-[#22D3EE]">{agent.name}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <Badge variant={agent.status === "ready" ? "success" : "muted"} dot={agent.status === "ready"} className="text-xs capitalize">
                {agent.status}
              </Badge>
            </div>
            {agent.created_at && <span className="mt-1 block truncate text-xs text-slate-400">Created: {formatDate(agent.created_at)}</span>}
          </div>
        </div>
      </div>
    </Link>
  );
}
