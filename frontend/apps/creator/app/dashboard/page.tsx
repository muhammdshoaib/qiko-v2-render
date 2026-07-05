"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Plus, Sparkles, Users, Zap, ArrowRight } from "lucide-react";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { createAgent, listAgents, markReady, type Agent } from "@/lib/api";

const WORKER_LIMIT = 3; // matches the qiko-frontend free-plan default

export default function DashboardPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const count = agents.data?.length ?? 0;
  const ready = agents.data?.filter((a) => a.status === "ready").length ?? 0;
  const atLimit = count >= WORKER_LIMIT;

  const create = useMutation({
    mutationFn: () => createAgent(name),
    onSuccess: () => { setName(""); qc.invalidateQueries({ queryKey: ["agents"] }); },
  });
  const markReadyMut = useMutation({
    mutationFn: (id: string) => markReady(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });

  return (
    <AppShell title="Dashboard">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>
              Welcome back
            </h2>
            <p className="text-sm text-muted-foreground">Your AI digital workers, at a glance.</p>
          </div>
          <Link href="/onboarding"><Button variant="outline"><Sparkles className="size-4" /> Guided setup</Button></Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { icon: Bot, label: "Workers", value: count, sub: `of ${WORKER_LIMIT} on your plan` },
            { icon: Zap, label: "Ready", value: ready, sub: "trained and live" },
            { icon: Users, label: "Plan", value: "Free", sub: "upgrade for more workers" },
          ].map((s) => (
            <Card key={s.label}>
              <CardContent className="pt-6 flex items-center gap-3">
                <span className="grid size-11 place-items-center rounded-xl bg-primary/10 text-primary"><s.icon className="size-5" /></span>
                <div>
                  <p className="text-xl font-semibold leading-tight">{s.value}</p>
                  <p className="text-xs text-muted-foreground">{s.label} — {s.sub}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardContent className="pt-6">
            <form onSubmit={(e) => { e.preventDefault(); if (name && !atLimit) create.mutate(); }} className="flex gap-2">
              <Input placeholder="New worker name…" value={name} onChange={(e) => setName(e.target.value)} disabled={atLimit} />
              <Button type="submit" disabled={create.isPending || atLimit}><Plus className="size-4" /> Create</Button>
            </form>
            {atLimit && <p className="mt-2 text-sm text-muted-foreground">You&apos;ve reached your plan&apos;s worker limit ({WORKER_LIMIT}). <Link href="/billing" className="text-primary hover:underline">Upgrade</Link> to add more.</p>}
            {create.isError && <p className="mt-2 text-sm text-destructive">Plan limit reached or not permitted.</p>}
          </CardContent>
        </Card>

        <div className="space-y-3">
          {agents.isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-[4.5rem] w-full" />)}
          {agents.data?.map((a: Agent) => (
            <Card key={a.id}>
              <CardContent className="flex items-center justify-between py-4">
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-lg bg-gradient-to-br from-primary to-secondary text-primary-foreground">
                    <Bot className="size-5" />
                  </span>
                  <div>
                    <Link href={`/workers/${a.id}`} className="font-medium hover:underline">{a.name}</Link>
                    <div><Badge variant={a.status === "ready" ? "success" : "muted"}>{a.status}</Badge></div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {a.status !== "ready" && (
                    <Button variant="outline" size="sm" onClick={() => markReadyMut.mutate(a.id)} disabled={markReadyMut.isPending}>
                      Mark ready
                    </Button>
                  )}
                  <Link href={`/workers/${a.id}`}><Button variant="ghost" size="sm"><ArrowRight className="size-4" /></Button></Link>
                </div>
              </CardContent>
            </Card>
          ))}
          {agents.data?.length === 0 && (
            <div className="py-12 text-center">
              <p className="text-sm text-muted-foreground mb-3">No workers yet — build your first AI expert.</p>
              <Link href="/onboarding"><Button><Sparkles className="size-4" /> Create your first worker</Button></Link>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
