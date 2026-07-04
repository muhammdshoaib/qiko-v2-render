"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Plus, Sparkles } from "lucide-react";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { createAgent, listAgents, markReady, type Agent } from "@/lib/api";

export default function DashboardPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });

  const create = useMutation({
    mutationFn: () => createAgent(name),
    onSuccess: () => { setName(""); qc.invalidateQueries({ queryKey: ["agents"] }); },
  });
  const ready = useMutation({
    mutationFn: (id: string) => markReady(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });

  return (
    <AppShell title="Workers">
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Your workers</h2>
            <p className="text-sm text-muted-foreground">Create and manage your AI workers.</p>
          </div>
          <Link href="/onboarding"><Button variant="outline"><Sparkles className="size-4" /> Guided setup</Button></Link>
        </div>

        <Card>
          <CardContent className="pt-6">
            <form onSubmit={(e) => { e.preventDefault(); if (name) create.mutate(); }} className="flex gap-2">
              <Input placeholder="New worker name…" value={name} onChange={(e) => setName(e.target.value)} />
              <Button type="submit" disabled={create.isPending}><Plus className="size-4" /> Create</Button>
            </form>
            {create.isError && <p className="mt-2 text-sm text-destructive">Plan limit reached or not permitted.</p>}
          </CardContent>
        </Card>

        <div className="space-y-3">
          {agents.isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-[4.5rem] w-full" />)}
          {agents.data?.map((a: Agent) => (
            <Card key={a.id}>
              <CardContent className="flex items-center justify-between py-4">
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-lg bg-accent text-accent-foreground">
                    <Bot className="size-5" />
                  </span>
                  <div>
                    <Link href={`/workers/${a.id}`} className="font-medium hover:underline">{a.name}</Link>
                    <div><Badge variant={a.status === "ready" ? "success" : "muted"}>{a.status}</Badge></div>
                  </div>
                </div>
                {a.status !== "ready" && (
                  <Button variant="outline" size="sm" onClick={() => ready.mutate(a.id)} disabled={ready.isPending}>
                    Mark ready
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
          {agents.data?.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">No workers yet — create your first one.</p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
