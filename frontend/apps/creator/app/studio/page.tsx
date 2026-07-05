"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Bot, Crown, Loader2, MessageSquare, Rocket, Star, Store, Target, TrendingUp, Trophy, Zap } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { listAgents, me, type Agent } from "@/lib/api";

const WORKER_LIMIT = 3;

function getRank(count: number) {
  if (count >= 10) return { title: "AI Mogul", icon: Crown, color: "text-amber-400", bg: "bg-amber-400/10" };
  if (count >= 5) return { title: "Team Lead", icon: Trophy, color: "text-purple-400", bg: "bg-purple-400/10" };
  if (count >= 3) return { title: "Rising Builder", icon: TrendingUp, color: "text-cyan-400", bg: "bg-cyan-400/10" };
  if (count >= 1) return { title: "First Hire", icon: Star, color: "text-emerald-400", bg: "bg-emerald-400/10" };
  return { title: "Getting Started", icon: Target, color: "text-slate-400", bg: "bg-slate-400/10" };
}

export default function StudioHome() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: listAgents });

  useEffect(() => {
    me().then((u) => setEmail(u.email)).catch(() => {});
  }, []);

  // Studio surfaces published/ready workers -- Creator ("/dashboard") is where they're built and trained.
  const published: Agent[] = useMemo(() => (agentsQ.data ?? []).filter((a) => a.status === "ready"), [agentsQ.data]);
  const totalWorkers = published.length;
  const rank = getRank(totalWorkers);
  const RankIcon = rank.icon;

  return (
    <AppShell title="Studio">
      {agentsQ.isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="size-6 animate-spin text-primary" />
        </div>
      ) : (
        <div className="mx-auto w-full max-w-5xl">
          {/* Hero */}
          <div className="relative mb-10 overflow-hidden rounded-2xl border border-white/5 bg-gradient-to-br from-[#0a0f1a] via-[#0d1425] to-[#0a0f1a]">
            <div className="pointer-events-none absolute right-0 top-0 h-72 w-72 rounded-full bg-primary/[0.08] blur-[100px]" />
            <div className="pointer-events-none absolute bottom-0 left-0 h-52 w-52 rounded-full bg-secondary/[0.06] blur-[80px]" />
            <div className="relative px-8 py-7">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-secondary text-xl font-bold text-white shadow-lg shadow-primary/20">
                    {(email || "Y").charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h1 className="text-xl font-bold text-white">{email ? `${email.split("@")[0]}'s` : "Your"} Team</h1>
                    <div className="mt-1 flex items-center gap-2">
                      <div className={`flex items-center gap-1 rounded-full px-2 py-0.5 ${rank.bg}`}>
                        <RankIcon className={`size-3 ${rank.color}`} />
                        <span className={`text-[10px] font-bold ${rank.color}`}>{rank.title}</span>
                      </div>
                      <span className="text-[10px] text-slate-600">·</span>
                      <span className="text-[10px] text-slate-500">{totalWorkers} active</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button className="flex items-center gap-2 rounded-xl border border-white/8 px-3.5 py-2 text-xs font-medium text-slate-400 transition-all hover:bg-white/5">
                    <Store className="size-3.5" />
                    Marketplace
                    <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-slate-600">Soon</span>
                  </button>
                  <button onClick={() => router.push("/dashboard")}
                    className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-primary/15 transition-all hover:opacity-90">
                    <Rocket className="size-3.5" /> Build a worker
                  </button>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-3 gap-3">
                <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.03] px-4 py-3">
                  <Zap className="size-4 text-amber-400" />
                  <div><p className="text-lg font-bold text-white">{agentsQ.data?.length ?? 0}</p><p className="text-[10px] text-slate-500">Total workers</p></div>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.03] px-4 py-3">
                  <Bot className="size-4 text-[#A78BFA]" />
                  <div><p className="text-lg font-bold text-white">{totalWorkers}</p><p className="text-[10px] text-slate-500">Published</p></div>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.03] px-4 py-3">
                  <MessageSquare className="size-4 text-primary" />
                  <div><p className="text-lg font-bold text-white">{Math.max(WORKER_LIMIT - totalWorkers, 0)}</p><p className="text-[10px] text-slate-500">Slots left</p></div>
                </div>
              </div>
            </div>
          </div>

          {/* Worker list */}
          {totalWorkers === 0 ? (
            <div className="flex flex-col items-center py-14">
              <div className="mb-5 flex size-14 items-center justify-center rounded-2xl border border-white/5 bg-gradient-to-br from-primary/20 to-secondary/20">
                <Rocket className="size-7 text-primary" />
              </div>
              <h3 className="mb-1.5 text-base font-bold text-white">Build & deploy your first worker</h3>
              <p className="mb-6 max-w-xs text-center text-sm text-slate-500">
                Build your worker on the Workers page, train it on your expertise, then it shows up here once it&apos;s ready.
              </p>
              <button onClick={() => router.push("/dashboard")}
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-all hover:opacity-90">
                <Rocket className="size-4" /> Build & deploy worker
              </button>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {published.map((w) => (
                <button key={w.id} onClick={() => router.push(`/studio/${w.id}`)}
                  className="flex items-center gap-3 rounded-xl border border-white/5 bg-[#0d1425] p-4 text-left transition-all hover:border-primary/30 hover:bg-white/[0.03]">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-secondary text-white">
                    <Bot className="size-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-white">{w.name}</p>
                    <p className="text-xs text-slate-500">Published · click to chat & research</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
