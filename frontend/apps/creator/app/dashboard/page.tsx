"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Brain, Lightbulb, Plus, Sparkles, Star } from "lucide-react";
import { Badge, Button, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { WorkerAvatar } from "@/components/worker-avatar";
import { createAgent, getAgentUsage, listAgents, me } from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

// Shared cockpit card surface (matches components/cockpit/* + outcomes-strip).
const CARD = "rounded-2xl border border-white/[0.06] bg-white/[0.015]";

// Small ramp-shaped sparkline under a stat value -- matches the live site's per-metric mini
// bar chart (11 bars, rising height + rising opacity left to right), color keyed per metric.
// Bars grow from the baseline (scaleY 0 -> 1) on mount, staggered left to right, matching the
// live-site entrance animation.
const SPARK_HEIGHTS = [30, 45, 35, 60, 50, 75, 65, 80, 70, 90, 85];
function Sparkline({ color }: { color: string }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <div className="flex h-6 items-end gap-0.5">
      {SPARK_HEIGHTS.map((h, i) => (
        <div
          key={i}
          className="flex-1 rounded-sm motion-reduce:!transform-none"
          style={{
            height: `${h}%`,
            background: color,
            opacity: 0.3 + (i / SPARK_HEIGHTS.length) * 0.65,
            transform: shown ? "scaleY(1)" : "scaleY(0)",
            transformOrigin: "center bottom",
            transition: "transform 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
            transitionDelay: `${200 + i * 50}ms`,
          }}
        />
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [atype, setAtype] = useState<"worker" | "pre_sales_writer" | "sales_intelligence" | "finance">("worker");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const usage = useQuery({ queryKey: ["agent-usage"], queryFn: getAgentUsage });
  const account = useQuery({ queryKey: ["me"], queryFn: me });
  const isViewer = account.data?.role === "viewer";  // read-only: cannot create workers (QIK-307)
  const workers = agents.data ?? [];
  const readyWorkers = workers.filter((a) => a.status === "ready");
  const trainingWorkers = workers.filter((a) => a.status !== "ready");
  const industries = useMemo(() => new Set(workers.map((a) => workerTypeLabel(a.atype))).size, [workers]);
  const workerLimit = usage.data?.worker_limit;
  const usedCount = usage.data?.used_count;
  const unlimited = workerLimit === -1;
  const atLimit = workerLimit !== undefined && !unlimited && (usedCount ?? 0) >= workerLimit;
  const creationBlocked = usage.isLoading || usage.isError || atLimit || isViewer;

  const create = useMutation({
    mutationFn: () => createAgent(name, atype),
    onSuccess: () => {
      setName("");
      setAtype("worker");
      setCreating(false);
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent-usage"] });
    },
  });

  const insights = useMemo(() => {
    const list: { title: string; body: string }[] = [];
    if (workers.length === 0) {
      list.push({ title: "Start with your first worker", body: "Create one worker to begin collecting conversations and performance insights." });
      return list;
    }
    if (readyWorkers.length === workers.length) {
      list.push({ title: "All workers are ready", body: "Great job. Your team is fully ready to handle conversations." });
    } else {
      list.push({ title: `${trainingWorkers.length} worker${trainingWorkers.length === 1 ? "" : "s"} still training`, body: "Finish training so they can go live and start handling conversations." });
    }
    const pct = Math.round((readyWorkers.length / workers.length) * 100);
    const slots = unlimited
      ? "Unlimited worker slots on your current plan."
      : usage.data
        ? `${Math.max(usage.data.worker_limit - usage.data.used_count, 0)} slots left on your current plan.`
        : "Plan usage is still being verified.";
    list.push({ title: `${pct}% of workers are ready`, body: slots });
    return list;
  }, [workers, readyWorkers, trainingWorkers, unlimited, usage.data]);

  return (
    <AppShell title="Dashboard">
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="mx-auto max-w-6xl">
          <div className="mb-8 flex items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-blue-500 shadow-lg shadow-cyan-500/20">
              <Brain className="size-5 text-white" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-white">Command Center</h1>
              <p className="text-sm text-slate-400">Your AI workforce at a glance</p>
            </div>
          </div>

          <div
            id="dashboard-worker-usage"
            role={usage.isError ? "alert" : "status"}
            aria-live={usage.isError ? "assertive" : "polite"}
            aria-busy={usage.isLoading}
            className="mb-6 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3 text-sm text-slate-300"
          >
            {usage.isLoading ? (
              <span>Checking plan usage...</span>
            ) : usage.isError ? (
              <span>
                Plan usage unavailable. Worker creation is paused. {" "}
                <button className="font-medium text-cyan-300 underline" onClick={() => usage.refetch()}>Retry</button>
              </span>
            ) : unlimited ? (
              <span>{usedCount ?? 0} worker slots used · Unlimited plan</span>
            ) : (
              <span>{usedCount ?? 0} of {workerLimit ?? 0} worker slots used{atLimit ? ". Limit reached." : "."}</span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <div className={cn("p-6", CARD)}>
                <p className="mb-5 text-[11px] font-semibold uppercase tracking-wider text-cyan-400">OUTCOMES &ndash; WORKFORCE</p>
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    { label: "Workers", value: workers.length, sparkColor: null },
                    { label: "Verticals", value: industries, sparkColor: null },
                    { label: "Ready", value: readyWorkers.length, sparkColor: "rgb(16,185,129)" },
                    { label: "Training", value: trainingWorkers.length, sparkColor: "rgb(251,191,36)" },
                  ].map((s) => (
                    <div key={s.label} className="flex flex-col gap-2">
                      <span className="text-3xl font-bold tracking-tight text-white">{s.value}</span>
                      <span className="text-[13px] text-slate-400">{s.label}</span>
                      {s.sparkColor && <Sparkline color={s.sparkColor} />}
                    </div>
                  ))}
                </div>
              </div>

              <div className={cn("p-6", CARD)}>
                <div className="mb-4 flex items-center gap-2">
                  <Sparkles className="size-4 text-cyan-400" />
                  <h2 className="text-sm font-semibold text-white">AI Insights</h2>
                </div>
                <div className="space-y-1">
                  {insights.map((i) => (
                    <div key={i.title} className="flex items-start gap-3 rounded-xl p-3 hover:bg-white/[0.03] transition-colors">
                      <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg" style={{ background: "rgba(16,185,129,0.125)" }}>
                        <Lightbulb className="size-4" style={{ color: "rgb(16,185,129)" }} />
                      </span>
                      <div>
                        <p className="text-sm font-medium text-white">{i.title}</p>
                        <p className="text-xs text-slate-400">{i.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-white">Your Workers</h2>
                  <Badge variant="success" className="text-[10px]">{readyWorkers.length} ready</Badge>
                </div>
                <Link href="/workers" className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs text-slate-400 hover:text-white">
                  View all <ArrowRight className="ml-1 size-3" />
                </Link>
              </div>

              <div className="space-y-3">
                {agents.isLoading && <p className="text-xs text-slate-400">Loading…</p>}
                {agents.isError && (
                  <p className="text-xs text-red-400">Couldn&apos;t load your workers. <button className="underline" onClick={() => agents.refetch()}>Retry</button></p>
                )}
                {workers.slice(0, 4).map((a) => (
                  <Link key={a.id} href={`/workers/${a.id}`} className="group relative block focus-visible:outline-none">
                    <div className={cn("relative overflow-hidden p-4 transition-colors duration-300 group-hover:bg-white/[0.03] group-focus-visible:ring-2 group-focus-visible:ring-cyan-500", CARD)}>
                      <div className="flex items-center gap-3">
                        <WorkerAvatar name={a.name} size="md" ready={a.status === "ready"} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="truncate font-semibold text-white">{a.name}</h3>
                            <Star className="size-3 shrink-0 fill-amber-400 text-amber-400" />
                          </div>
                          <p className="truncate text-xs text-slate-400">{workerTypeLabel(a.atype)}</p>
                        </div>
                        <ArrowRight className="size-4 shrink-0 text-slate-500 transition-colors group-hover:text-cyan-400" />
                      </div>
                    </div>
                  </Link>
                ))}
                {workers.length === 0 && !agents.isLoading && (
                  <p className="text-xs text-slate-400">No workers yet.</p>
                )}

                {creating ? (
                  <div className="space-y-2 pt-1">
                    <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="New worker name..."
                      onKeyDown={(e) => { if (e.key === "Enter" && name && !create.isPending) create.mutate(); if (e.key === "Escape") setCreating(false); }}
                      className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 transition-colors focus-visible:border-cyan-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500" />
                    <div className="grid grid-cols-2 gap-2">
                      {([
                        { key: "worker", label: "AI Worker", desc: "Grounded chat, research & knowledge" },
                        { key: "pre_sales_writer", label: "Pre-Sales Writer", desc: "Tender bids, compliance, win/loss" },
                        { key: "sales_intelligence", label: "Sales Intelligence", desc: "Tender ingestion + Salesforce" },
                        { key: "finance", label: "Financial Analyst", desc: "Excel portfolio analytics" },
                      ] as const).map((t) => (
                        <button key={t.key} type="button" onClick={() => setAtype(t.key)}
                          className={cn("rounded-lg border p-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500",
                            atype === t.key ? "border-cyan-500/50 bg-cyan-500/10" : "border-white/10 hover:border-white/20")}>
                          <span className="block text-xs font-semibold text-white">{t.label}</span>
                          <span className="block text-[10px] text-slate-400">{t.desc}</span>
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Button className="flex-1 bg-gradient-to-r from-violet-500 to-cyan-400 text-white hover:opacity-90" disabled={creationBlocked || !name || create.isPending} aria-describedby="dashboard-worker-usage" onClick={() => create.mutate()}>
                        <Plus className="size-4" /> Create
                      </Button>
                      <Button variant="outline" onClick={() => { setCreating(false); setName(""); }}>Cancel</Button>
                    </div>
                    {create.isError && <p className="text-xs text-destructive">Plan limit reached or not permitted.</p>}
                  </div>
                ) : (
                  <button onClick={() => setCreating(true)} disabled={creationBlocked} aria-describedby="dashboard-worker-usage"
                    className="group w-full rounded-2xl border border-dashed border-white/10 p-4 transition-colors hover:border-cyan-500/50 hover:bg-cyan-500/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 disabled:opacity-50">
                    <div className="flex items-center justify-center gap-2">
                      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-white/5 transition-colors group-hover:bg-cyan-500/20">
                        <Plus className="size-4 text-slate-400 group-hover:text-cyan-400" />
                      </span>
                      <span className="text-sm text-slate-400 transition-colors group-hover:text-white">New Worker</span>
                    </div>
                  </button>
                )}
              </div>

              <div className="rounded-2xl border border-cyan-500/20 bg-gradient-to-br from-cyan-500/10 to-violet-500/[0.06] p-4">
                <div className="flex items-start gap-3">
                  <Lightbulb className="mt-0.5 size-4 shrink-0 text-cyan-400" />
                  <div>
                    <p className="text-xs font-medium text-white">Pro tip</p>
                    <p className="mt-0.5 text-xs text-slate-400">Train your worker with real conversations for best results</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
