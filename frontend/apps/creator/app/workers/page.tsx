"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Badge, Button } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { createAgent, listAgents, type Agent } from "@/lib/api";

const WORKER_LIMIT = 3;

function workerCategory(a: Agent): string {
  const expertise = a.config?.expertise as string | undefined;
  return expertise?.trim() || "General";
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
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>
            Your <span className="text-primary">Workers</span>
          </h1>
          <p className="text-sm text-muted-foreground">{workers.length} active worker{workers.length === 1 ? "" : "s"}</p>
        </div>
        <div className="flex items-center gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New worker name..."
            className="w-56 rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          <Button disabled={atLimit || !name || create.isPending} onClick={() => create.mutate()}>
            <Plus className="size-4" /> Create Worker
          </Button>
        </div>
      </div>
      {create.isError && <p className="mb-4 text-sm text-destructive">Plan limit reached or not permitted.</p>}

      {agents.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!agents.isLoading && workers.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-sm text-muted-foreground mb-3">No workers yet — build your first AI expert.</p>
        </div>
      )}

      <div className="space-y-8">
        {groups.map(([category, items]) => (
          <div key={category}>
            <div className="mb-3">
              <h2 className="text-sm font-semibold">{category}</h2>
              <p className="text-xs text-muted-foreground">{items.length} worker{items.length === 1 ? "" : "s"}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((a) => (
                <WorkerCard key={a.id} agent={a} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </AppShell>
  );
}

function WorkerCard({ agent }: { agent: Agent }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-card">
      <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-primary via-secondary to-primary" />
      <Link href={`/workers/${agent.id}`} className="block p-4">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-primary to-secondary text-sm font-bold text-white">
            {agent.name.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{agent.name}</p>
            <Badge variant={agent.status === "ready" ? "success" : "muted"} className="mt-1">{agent.status}</Badge>
          </div>
        </div>
      </Link>
    </div>
  );
}
