"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Brain, Lightbulb, Plus, Sparkles, Target } from "lucide-react";
import { Button, Card, CardContent } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { createAgent, listAgents, type Agent } from "@/lib/api";

const WORKER_LIMIT = 3; // matches the qiko-frontend free-plan default

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

  return (
    <AppShell title="Dashboard">
      <div className="flex items-start gap-3 mb-6">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-secondary text-white">
          <Brain className="size-5" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Command Center</h1>
          <p className="text-sm text-muted-foreground">Your AI workforce at a glance</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_22rem] gap-6">
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-6 grid grid-cols-2 sm:grid-cols-4 gap-6">
              {[
                { label: "Workers", value: workers.length },
                { label: "Industries", value: industries },
                { label: "Ready", value: readyWorkers.length },
                { label: "Training", value: trainingWorkers.length },
              ].map((s) => (
                <div key={s.label}>
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{s.label}</p>
                  <p className="mt-1 text-2xl font-semibold">{s.value}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="size-4 text-primary" /> AI Insights
              </div>
              <div className="space-y-3">
                {insights.map((i) => (
                  <div key={i.title} className="flex items-start gap-3 rounded-lg border border-border/60 p-3">
                    <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                      <Lightbulb className="size-3.5" />
                    </span>
                    <div>
                      <p className="text-sm font-medium">{i.title}</p>
                      <p className="text-xs text-muted-foreground">{i.body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardContent className="pt-6 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Your Workers</h2>
                <Link href="/workers" className="text-xs font-medium text-primary hover:underline">View all →</Link>
              </div>
              {agents.isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
              {readyWorkers.slice(0, 4).map((a) => (
                <Link key={a.id} href={`/workers/${a.id}`}
                  className="flex items-center gap-3 rounded-lg border border-border/60 p-3 hover:bg-muted/50 transition-colors">
                  <span className="relative grid size-9 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-primary to-secondary text-white">
                    <Bot className="size-4" />
                    <span className="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border-2 border-background bg-emerald-500" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{a.name}</p>
                    <p className="truncate text-xs text-muted-foreground">{workerCategory(a)}</p>
                  </div>
                </Link>
              ))}
              {workers.length === 0 && !agents.isLoading && (
                <p className="text-xs text-muted-foreground">No workers yet.</p>
              )}
              <div className="space-y-2 pt-1">
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New worker name..."
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                <Button className="w-full" disabled={atLimit || !name || create.isPending} onClick={() => create.mutate()}>
                  <Plus className="size-4" /> New Worker
                </Button>
                {create.isError && <p className="text-xs text-destructive">Plan limit reached or not permitted.</p>}
              </div>
            </CardContent>
          </Card>

          <Card className="border-primary/20 bg-primary/[0.04]">
            <CardContent className="pt-6 flex items-start gap-3">
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                <Target className="size-4" />
              </span>
              <div>
                <p className="text-sm font-medium">Pro tip</p>
                <p className="text-xs text-muted-foreground">Train your worker with real conversations for best results</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
