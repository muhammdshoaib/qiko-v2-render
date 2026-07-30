"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Badge, Button } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { WorkerAvatar, workerTypeIcon } from "@/components/worker-avatar";
import { createAgent, getAgentUsage, listAgents, type Agent } from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

// Per-type tint for the workers-list GROUP header icon (matches idg-sales.qiko.ai: a small coloured
// per-vertical icon next to the humanised label). The per-worker avatar stays a cyan->blue letter.
function groupIconTint(atype: string): string {
  switch (atype.trim()) {
    case "sales_intelligence":
      return "border-teal-500/30 bg-teal-500/10 text-teal-400";
    case "pre_sales_writer":
      return "border-cyan-500/30 bg-cyan-500/10 text-cyan-400";
    case "finance":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    default:
      return "border-violet-500/30 bg-violet-500/10 text-violet-400";
  }
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
  const usage = useQuery({ queryKey: ["agent-usage"], queryFn: getAgentUsage });
  const workers = agents.data ?? [];
  const workerLimit = usage.data?.worker_limit;
  const usedCount = usage.data?.used_count;
  const unlimited = workerLimit === -1;
  const atLimit = workerLimit !== undefined && !unlimited && (usedCount ?? 0) >= workerLimit;
  const usageText = usage.isLoading
    ? "Checking plan usage..."
    : usage.isError
      ? "Plan usage unavailable"
      : unlimited
        ? `${usedCount ?? 0} worker slots used · Unlimited plan`
        : `${usedCount ?? 0} / ${workerLimit ?? 0} worker slots used`;

  const create = useMutation({
    mutationFn: () => createAgent(name),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent-usage"] });
    },
  });

  // Group by worker vertical (atype) so the section headers read as the humanised vertical
  // ("AI Worker", "Pre-Sales Writer", ...) instead of a free-text / "General" expertise string.
  const groups = useMemo(() => {
    const byType = new Map<string, Agent[]>();
    for (const a of workers) {
      const key = (a.atype ?? "").trim() || "worker";
      byType.set(key, [...(byType.get(key) ?? []), a]);
    }
    return Array.from(byType.entries());
  }, [workers]);

  return (
    <AppShell title="Workers">
      <div className="relative flex flex-col gap-4 border-b border-white/[0.06] bg-[#070a12]/80 px-4 py-4 backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-6">
        <div>
          <h1 className="mb-1 text-2xl font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>
            Your Workers
          </h1>
          <p
            id="workers-plan-usage"
            role={usage.isError ? "alert" : "status"}
            aria-live={usage.isError ? "assertive" : "polite"}
            aria-busy={usage.isLoading}
            className="text-sm text-slate-400"
          >
            {workers.length} active worker{workers.length === 1 ? "" : "s"} · {usageText}
          </p>
        </div>
        <div className="flex w-full items-center justify-start gap-3 sm:w-auto sm:justify-end">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New worker name..."
            aria-label="New worker name"
            className="w-56 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 transition-colors focus-visible:border-cyan-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500" />
          <Button disabled={usage.isLoading || usage.isError || atLimit || !name || create.isPending} aria-describedby="workers-plan-usage" onClick={() => create.mutate()}
            className="rounded-xl bg-gradient-to-r from-violet-500 to-cyan-400 font-medium text-white shadow-lg shadow-cyan-500/20 hover:opacity-90">
            <Plus className="size-4" /> Create Worker
          </Button>
        </div>
      </div>

      <div className="p-4 sm:p-6 lg:p-8">
        {create.isError && <p className="mb-4 text-sm text-destructive">Plan limit reached or not permitted.</p>}
        {agents.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {agents.isError && (
          <p className="mb-4 text-sm text-destructive">Couldn&apos;t load your workers. <button className="underline" onClick={() => agents.refetch()}>Retry</button></p>
        )}
        {usage.isError && (
          <p role="alert" className="mb-4 text-sm text-amber-300">
            Couldn&apos;t load plan usage. Creation is paused until usage is verified. {" "}
            <button className="underline" onClick={() => usage.refetch()}>Retry</button>
          </p>
        )}
        {atLimit && (
          <p className="mb-4 text-sm text-amber-300">Your plan worker limit is reached. Existing disabled workers still use a plan slot.</p>
        )}

        {!agents.isLoading && !agents.isError && workers.length === 0 && (
          <div className="py-16 text-center">
            <p className="text-sm text-muted-foreground mb-3">No workers yet - build your first AI expert.</p>
          </div>
        )}

        <div className="mx-auto max-w-6xl space-y-8 sm:space-y-10">
          {groups.map(([atype, items]) => {
            const GroupIcon = workerTypeIcon(atype);
            return (
              <div key={atype}>
                <div className="mb-4 flex items-center gap-3">
                  <span className={`flex size-10 items-center justify-center rounded-xl border ${groupIconTint(atype)}`}>
                    <GroupIcon className="size-5" aria-hidden="true" />
                  </span>
                  <div>
                    <h2 className="text-lg font-semibold text-white">{workerTypeLabel(atype)}</h2>
                    <p className="text-xs text-slate-500">{items.length} worker{items.length === 1 ? "" : "s"}</p>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {items.map((a) => (
                    <WorkerCard key={a.id} agent={a} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}

function WorkerCard({ agent }: { agent: Agent }) {
  return (
    <Link href={`/workers/${agent.id}`} className="group block cursor-pointer rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500">
      <div className="relative overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.015] py-2 backdrop-blur-xl transition-colors group-hover:bg-white/[0.03]">
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cyan-400 to-violet-500" />
        <div className="flex items-start gap-4 p-5">
          <WorkerAvatar name={agent.name} size="lg" ready={agent.status === "ready"} />
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-semibold capitalize text-white transition-colors group-hover:text-cyan-300">{agent.name}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <Badge variant={agent.status === "ready" ? "success" : "muted"} dot={agent.status === "ready"} className="text-xs capitalize">
                {agent.status}
              </Badge>
              <Badge variant="muted" className="text-xs">{workerTypeLabel(agent.atype)}</Badge>
            </div>
            {agent.created_at && <span className="mt-1 block truncate text-xs text-slate-400">Created: {formatDate(agent.created_at)}</span>}
          </div>
        </div>
      </div>
    </Link>
  );
}
