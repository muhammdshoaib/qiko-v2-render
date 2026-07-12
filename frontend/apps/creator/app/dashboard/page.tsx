"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Brain, Lightbulb, Plus, Sparkles } from "lucide-react";
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

export default function DashboardPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const workers = agents.data ?? [];
  const readyWorkers = workers.filter((a) => a.status === "ready");
  const trainingWorkers = workers.filter((a) => a.status !== "ready");
  const industries = useMemo(() => new Set(workers.map(workerCategory)).size, [workers]);
  const atLimit = workers.length >= WORKER_LIMIT;

  const create = useMutation({
    mutationFn: () => createAgent(name),
    onSuccess: () => { setName(""); qc.invalidateQueries({ queryKey: ["agents"] }); },
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
                  { label: "Workers", value: workers.length },
                  { label: "Industries", value: industries },
                  { label: "Ready", value: readyWorkers.length },
                  { label: "Training", value: trainingWorkers.length },
                ].map((s) => (
                  <div key={s.label} className="flex flex-col gap-2">
                    <span className="text-xs uppercase tracking-wider text-slate-500">{s.label}</span>
                    <span className="text-2xl font-bold text-white">{s.value}</span>
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
                      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[#6366F1]/10 text-[#6366F1]">
                        <Lightbulb className="size-3.5" />
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
                            <h3 className="truncate font-semibold text-white">{a.name}</h3>
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

                <div className="space-y-2 pt-1">
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New worker name..."
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                  <Button className="w-full bg-gradient-to-r from-[#6366F1] to-[#22D3EE] hover:opacity-90" disabled={atLimit || !name || create.isPending} onClick={() => create.mutate()}>
                    <Plus className="size-4" /> New Worker
                  </Button>
                  {create.isError && <p className="text-xs text-destructive">Plan limit reached or not permitted.</p>}
                </div>
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
