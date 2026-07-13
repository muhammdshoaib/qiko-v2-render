"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Brain, Lightbulb, Plus, Sparkles, Star } from "lucide-react";
import { Badge, Button } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { createAgent, listAgents, type Agent } from "@/lib/api";

const WORKER_LIMIT = 3; // matches the qiko-frontend free-plan default

const EMOJIS = ["🚀", "🤖", "⚡", "🎯", "💡", "🛡️", "📊", "🧭"];
const AVATAR_GRADIENTS = [
  "from-violet-500 to-purple-600", "from-cyan-500 to-blue-500", "from-emerald-500 to-teal-500",
  "from-amber-500 to-orange-600", "from-pink-500 to-rose-500", "from-indigo-500 to-blue-600",
];
function hashOf(id: string): number {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash;
}

function workerCategory(a: Agent): string {
  const expertise = a.config?.expertise as string | undefined;
  return expertise?.trim() || "General";
}

// Small ramp-shaped sparkline under a stat value -- matches the live site's per-metric mini
// bar chart (11 bars, rising height + rising opacity left to right), color keyed per metric.
const SPARK_HEIGHTS = [30, 45, 35, 60, 50, 75, 65, 80, 70, 90, 85];
function Sparkline({ color }: { color: string }) {
  return (
    <div className="flex h-6 items-end gap-0.5">
      {SPARK_HEIGHTS.map((h, i) => (
        <div key={i} className="flex-1 rounded-sm" style={{ height: `${h}%`, background: color, opacity: 0.3 + (i / SPARK_HEIGHTS.length) * 0.65 }} />
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [atype, setAtype] = useState<"worker" | "sales_intelligence" | "finance">("worker");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const workers = agents.data ?? [];
  const readyWorkers = workers.filter((a) => a.status === "ready");
  const trainingWorkers = workers.filter((a) => a.status !== "ready");
  const industries = useMemo(() => new Set(workers.map(workerCategory)).size, [workers]);
  const atLimit = workers.length >= WORKER_LIMIT;

  const create = useMutation({
    mutationFn: () => createAgent(name, atype),
    onSuccess: () => { setName(""); setAtype("worker"); setCreating(false); qc.invalidateQueries({ queryKey: ["agents"] }); },
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
    list.push({ title: `${pct}% of workers are ready`, body: `${Math.max(WORKER_LIMIT - workers.length, 0)} slots left on your current plan.` });
    return list;
  }, [workers, readyWorkers, trainingWorkers]);

  const cardStyle = { background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" };

  return (
    <AppShell title="Dashboard">
      <div className="p-6 lg:p-8">
        <div className="mx-auto max-w-6xl">
          <div className="mb-8 flex items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-[#6366F1] to-[#22D3EE]">
              <Brain className="size-5 text-white" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-white">Command Center</h1>
              <p className="text-sm text-slate-400">Your AI workforce at a glance</p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <div className="grid grid-cols-2 gap-6 rounded-2xl p-5 md:grid-cols-4" style={cardStyle}>
                {[
                  { label: "Workers", value: workers.length, sparkColor: null },
                  { label: "Industries", value: industries, sparkColor: null },
                  { label: "Ready", value: readyWorkers.length, sparkColor: "rgb(16,185,129)" },
                  { label: "Training", value: trainingWorkers.length, sparkColor: "rgb(255,185,0)" },
                ].map((s) => (
                  <div key={s.label} className="flex flex-col gap-2">
                    <span className="text-xs uppercase tracking-wider text-slate-500">{s.label}</span>
                    <span className="text-2xl font-bold text-white">{s.value}</span>
                    {s.sparkColor && <Sparkline color={s.sparkColor} />}
                  </div>
                ))}
              </div>

              <div className="rounded-2xl p-5" style={cardStyle}>
                <div className="mb-4 flex items-center gap-2">
                  <Sparkles className="size-4 text-[#6366F1]" />
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
                {workers.slice(0, 4).map((a) => {
                  const h = hashOf(a.id);
                  return (
                    <Link key={a.id} href={`/workers/${a.id}`} className="group relative block">
                      <div className="relative overflow-hidden rounded-2xl p-4 transition-all duration-300 hover:border-white/10" style={cardStyle}>
                        <div className="flex items-center gap-3">
                          <div className={`relative flex size-12 items-center justify-center rounded-xl bg-gradient-to-br ${AVATAR_GRADIENTS[h % AVATAR_GRADIENTS.length]} text-xl`}>
                            <span>{EMOJIS[h % EMOJIS.length]}</span>
                            {a.status === "ready" && (
                              <span className="absolute -bottom-0.5 -right-0.5 size-4 rounded-full border-2 border-[#0a0f1a] bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <h3 className="truncate font-semibold text-white">{a.name}</h3>
                              <Star className="size-3 shrink-0 fill-amber-400 text-amber-400" />
                            </div>
                            <p className="truncate text-xs text-slate-400">{workerCategory(a)}</p>
                          </div>
                          <ArrowRight className="size-4 shrink-0 text-slate-500 transition-all group-hover:text-[#22D3EE]" />
                        </div>
                      </div>
                    </Link>
                  );
                })}
                {workers.length === 0 && !agents.isLoading && (
                  <p className="text-xs text-slate-400">No workers yet.</p>
                )}

                {creating ? (
                  <div className="space-y-2 pt-1">
                    <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="New worker name..."
                      onKeyDown={(e) => { if (e.key === "Enter" && name && !create.isPending) create.mutate(); if (e.key === "Escape") setCreating(false); }}
                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                    <div className="grid grid-cols-2 gap-2">
                      {([
                        { key: "worker", label: "General worker", desc: "Chat, knowledge, RFP" },
                        { key: "sales_intelligence", label: "Sales Intelligence", desc: "Tender ingestion + Salesforce" },
                        { key: "finance", label: "Financial Analyst", desc: "Excel portfolio analytics" },
                      ] as const).map((t) => (
                        <button key={t.key} type="button" onClick={() => setAtype(t.key)}
                          className={`rounded-lg border p-2 text-left transition-colors ${atype === t.key ? "border-[#6366F1] bg-[#6366F1]/10" : "border-white/10 hover:border-white/20"}`}>
                          <span className="block text-xs font-semibold text-white">{t.label}</span>
                          <span className="block text-[10px] text-slate-400">{t.desc}</span>
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Button className="flex-1 bg-gradient-to-r from-[#6366F1] to-[#22D3EE] hover:opacity-90" disabled={atLimit || !name || create.isPending} onClick={() => create.mutate()}>
                        <Plus className="size-4" /> Create
                      </Button>
                      <Button variant="outline" onClick={() => { setCreating(false); setName(""); }}>Cancel</Button>
                    </div>
                    {create.isError && <p className="text-xs text-destructive">Plan limit reached or not permitted.</p>}
                  </div>
                ) : (
                  <button onClick={() => setCreating(true)} disabled={atLimit}
                    className="group w-full rounded-2xl border border-dashed border-white/10 p-4 transition-all hover:border-[#6366F1]/50 hover:bg-[#6366F1]/5 disabled:opacity-50">
                    <div className="flex items-center justify-center gap-2">
                      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-white/5 transition-colors group-hover:bg-[#6366F1]/20">
                        <Plus className="size-4 text-slate-400 group-hover:text-[#6366F1]" />
                      </span>
                      <span className="text-sm text-slate-400 transition-colors group-hover:text-white">New Worker</span>
                    </div>
                  </button>
                )}
              </div>

              <div className="rounded-xl p-4" style={{ background: "linear-gradient(135deg, rgba(99,102,241,0.1), rgba(34,211,238,0.05))", border: "1px solid rgba(99,102,241,0.2)" }}>
                <div className="flex items-start gap-3">
                  <span className="text-lg">💡</span>
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
