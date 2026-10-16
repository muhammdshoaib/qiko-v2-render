"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@qiko/ui";
import { WorkerChatTab } from "@/components/worker-cockpit-tabs";
import { BLOCK_AGENTS } from "@/components/knowledge/investors-data";
import { createAgent, type Agent } from "@/lib/api";

function matchAgent(agents: Agent[], blockName: string) {
  const needle = blockName.toLowerCase();
  return (
    agents.find((a) => a.name.toLowerCase() === needle) ??
    agents.find((a) => a.name.toLowerCase().includes(needle))
  );
}

export function InvestorsChat({ agents, agentsLoading }: { agents: Agent[]; agentsLoading: boolean }) {
  const qc = useQueryClient();
  const [selectedBlockId, setSelectedBlockId] = useState(BLOCK_AGENTS[0]!.id);
  const selectedBlock = BLOCK_AGENTS.find((a) => a.id === selectedBlockId) ?? BLOCK_AGENTS[0]!;
  const attempted = useRef<Set<string>>(new Set());

  const worker = useMemo(() => matchAgent(agents, selectedBlock.name), [agents, selectedBlock.name]);

  const ensure = useMutation({
    mutationFn: (name: string) => createAgent(name, "intelligence"),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["agents"] });
      await qc.invalidateQueries({ queryKey: ["agent-usage"] });
    },
  });

  useEffect(() => {
    if (agentsLoading || worker) return;
    if (attempted.current.has(selectedBlock.name) || ensure.isPending) return;
    attempted.current.add(selectedBlock.name);
    ensure.mutate(selectedBlock.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only auto-create once per block agent name
  }, [agentsLoading, worker, selectedBlock.name]);

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap gap-2">
        {BLOCK_AGENTS.map((agent) => {
          const active = agent.id === selectedBlockId;
          return (
            <button
              key={agent.id}
              type="button"
              onClick={() => setSelectedBlockId(agent.id)}
              className={cn(
                "rounded-xl border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                active
                  ? "border-indigo-200 bg-indigo-50 text-indigo-800"
                  : "border-border bg-muted/50 text-slate-600 hover:border-border hover:text-foreground",
              )}
            >
              <div className="text-[13px] font-semibold">{agent.name}</div>
              <div className="text-[11px] text-slate-500">{agent.role}</div>
            </button>
          );
        })}
      </div>

      {worker ? (
        <WorkerChatTab key={worker.id} id={worker.id} worker={worker} />
      ) : (
        <div className="rounded-2xl border border-border bg-card p-6">
          <div className="mb-4 flex min-h-48 flex-col items-center justify-center rounded-lg border border-border bg-muted/50 text-center">
            <p className="text-sm font-medium text-slate-700">
              {agentsLoading || ensure.isPending ? `Starting ${selectedBlock.name}…` : "Preparing chat"}
            </p>
            <p className="mt-1 max-w-sm text-xs text-slate-500">
              Setting up this Investors agent so you can test replies here.
            </p>
            {ensure.isError && (
              <button
                type="button"
                className="mt-4 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
                onClick={() => {
                  attempted.current.delete(selectedBlock.name);
                  ensure.mutate(selectedBlock.name);
                }}
              >
                Retry
              </button>
            )}
          </div>
          <div className="flex gap-2 opacity-40">
            <div className="h-10 flex-1 rounded-md border border-border bg-muted" />
            <div className="h-10 w-11 rounded-md bg-indigo-600/40" />
          </div>
        </div>
      )}
    </div>
  );
}
