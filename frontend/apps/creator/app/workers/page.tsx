"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpen, Plus, Sparkles } from "lucide-react";
import { Badge, Button } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { WorkerAvatar, workerTypeIcon } from "@/components/worker-avatar";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { INVESTORS_BLOCK } from "@/components/knowledge/investors-data";
import { createAgent, getAgentUsage, listAgents, me, updateAgentConfig, type Agent } from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

function groupIconTint(atype: string): string {
  switch (atype.trim()) {
    case "sales_intelligence":
      return "border-teal-500/30 bg-teal-500/10 text-teal-400";
    case "pre_sales_writer":
      return "border-cyan-500/30 bg-cyan-500/10 text-cyan-400";
    case "finance":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    case "intelligence":
      return "border-amber-500/30 bg-amber-500/10 text-amber-400";
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

export default function KnowledgePage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const usage = useQuery({ queryKey: ["agent-usage"], queryFn: getAgentUsage });
  const workers = agents.data ?? [];
  const workerLimit = usage.data?.worker_limit;
  const usedCount = usage.data?.used_count;
  const unlimited = workerLimit === -1;
  const atLimit = workerLimit !== undefined && !unlimited && (usedCount ?? 0) >= workerLimit;
  const account = useQuery({ queryKey: ["me"], queryFn: me });
  const isViewer = account.data?.role === "viewer";

  const create = useMutation({
    mutationFn: () => createAgent(name),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent-usage"] });
    },
  });

  const groups = useMemo(() => {
    const byType = new Map<string, Agent[]>();
    for (const a of workers) {
      const key = (a.atype ?? "").trim() || "worker";
      byType.set(key, [...(byType.get(key) ?? []), a]);
    }
    return Array.from(byType.entries());
  }, [workers]);

  return (
    <AppShell title="Knowledge">
      <div className="relative flex flex-col gap-4 border-b border-white/[0.06] bg-[#070a12]/80 px-4 py-4 backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-6">
        <div>
          <h1 className="mb-1 text-2xl font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>
            All knowledge blocks
          </h1>
          <p className="text-sm text-slate-400">
            Knowledge blocks the customer has bought. Agents are reached through their block.
          </p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      <div className="p-4 sm:p-6 lg:p-8">
        <div className="mx-auto max-w-6xl space-y-8">
          <section aria-label="Knowledge blocks">
            <div className="mb-4 flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-xl border border-indigo-500/30 bg-indigo-500/10 text-indigo-300">
                <BookOpen className="size-5" />
              </span>
              <div>
                <h2 className="text-lg font-semibold text-white">Joseph Mews</h2>
                <p className="text-xs text-slate-500">1 knowledge block</p>
              </div>
            </div>

            <Link
              href="/knowledge/investors"
              className="group block rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5 transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-lg font-semibold text-white group-hover:text-cyan-300">{INVESTORS_BLOCK.name}</h3>
                    <Badge variant="muted" className="text-xs">{INVESTORS_BLOCK.kind}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-400">
                    {INVESTORS_BLOCK.agents} agents · value this month {INVESTORS_BLOCK.valueThisMonth} ·{" "}
                    {INVESTORS_BLOCK.conversations} conversations · {INVESTORS_BLOCK.handedToCrm} handed to CRM
                  </p>
                </div>
                <span className="inline-flex items-center gap-1 text-sm text-slate-400 group-hover:text-cyan-300">
                  Open block <ArrowRight className="size-4" />
                </span>
              </div>
            </Link>

            <div className="mt-4 rounded-2xl border border-dashed border-white/10 p-5 text-sm text-slate-500">
              Room for more knowledge blocks later.
            </div>
          </section>

          <section aria-label="Other worker cards">
            <div className="mb-4 flex items-center gap-2">
              <Sparkles className="size-4 text-violet-300" />
              <h2 className="text-sm font-semibold text-white">Qiko-Sonic and Custom cards</h2>
              <span className="text-xs text-slate-500">Can stay as they are for now</span>
            </div>

            {!isViewer && (
              <div className="mb-6 flex w-full flex-col items-stretch gap-3 sm:flex-row sm:items-center">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="New worker name..."
                  aria-label="New worker name"
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 transition-colors focus-visible:border-cyan-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 sm:w-56"
                />
                <Button
                  disabled={usage.isLoading || usage.isError || atLimit || !name || create.isPending}
                  onClick={() => create.mutate()}
                  className="min-h-11 w-full rounded-xl bg-gradient-to-r from-violet-500 to-cyan-400 font-medium text-white shadow-lg shadow-cyan-500/20 hover:opacity-90 sm:min-h-9 sm:w-auto"
                >
                  <Plus className="size-4" /> Create Worker
                </Button>
              </div>
            )}

            {agents.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
            {agents.isError && (
              <p className="mb-4 text-sm text-destructive">
                Couldn&apos;t load workers. <button className="underline" onClick={() => agents.refetch()}>Retry</button>
              </p>
            )}

            <div className="space-y-8 sm:space-y-10">
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
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function WorkerCard({ agent }: { agent: Agent }) {
  const qc = useQueryClient();
  const ready = agent.status === "ready";
  const studioLinked = agent.config?.studio_linked === true;
  const pushStudio = useMutation({
    mutationFn: () => updateAgentConfig(agent.id, { studio_linked: !studioLinked }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.015] py-2 backdrop-blur-xl transition-colors hover:bg-white/[0.03]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cyan-400 to-violet-500" />
      <div className="flex items-start gap-4 p-5">
        <Link href={`/workers/${agent.id}`} className="flex min-w-0 flex-1 items-start gap-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500">
          <WorkerAvatar name={agent.name} size="lg" ready={ready} />
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-semibold capitalize text-white transition-colors group-hover:text-cyan-300">{agent.name}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <Badge variant={ready ? "success" : "muted"} dot={ready} className="text-xs capitalize">
                {agent.status}
              </Badge>
              <Badge variant="muted" className="text-xs">{workerTypeLabel(agent.atype)}</Badge>
            </div>
            {agent.created_at && <span className="mt-1 block truncate text-xs text-slate-400">Created: {formatDate(agent.created_at)}</span>}
          </div>
        </Link>
        <div className="flex flex-col items-end gap-2">
          <Button
            variant={studioLinked ? "outline" : "default"}
            size="sm"
            disabled={!ready || pushStudio.isPending}
            title={!ready ? "Make the worker Ready before pushing it to Studio" : studioLinked ? "Remove from Studio" : "Push to Studio"}
            onClick={() => pushStudio.mutate()}
          >
            {pushStudio.isPending ? "Saving…" : studioLinked ? "In Studio" : "Push to Studio"}
          </Button>
          {pushStudio.isError && <span className="text-xs text-red-500">Failed</span>}
        </div>
      </div>
    </div>
  );
}
