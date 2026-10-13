"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BarChart3,
  Database,
  GraduationCap,
  Link2,
  MessageSquare,
  Settings,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { InvestorsAnalytics } from "@/components/knowledge/investors-analytics";
import { InvestorsOverview } from "@/components/knowledge/investors-overview";
import { BLOCK_AGENTS, INVESTORS_BLOCK } from "@/components/knowledge/investors-data";
import { listAgents } from "@/lib/api";

type Tab = "Overview" | "Analytics" | "Chat" | "Train" | "Sources" | "CRM" | "Connections" | "Settings";

const TABS: { id: Tab; icon: LucideIcon }[] = [
  { id: "Overview", icon: Sparkles },
  { id: "Analytics", icon: BarChart3 },
  { id: "Chat", icon: MessageSquare },
  { id: "Train", icon: GraduationCap },
  { id: "Sources", icon: Database },
  { id: "CRM", icon: Users },
  { id: "Connections", icon: Link2 },
  { id: "Settings", icon: Settings },
];

export default function InvestorsKnowledgePage() {
  const [tab, setTab] = useState<Tab>("Overview");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const linkedAgentId = useMemo(() => {
    const list = agents.data ?? [];
    const match = list.find((agent) => /intent|intelligence|investor/i.test(`${agent.name} ${agent.atype}`));
    return match?.id ?? list[0]?.id;
  }, [agents.data]);

  return (
    <AppShell title="Investors">
      <div className="flex min-w-0 flex-col overflow-x-hidden">
        <div className="relative min-w-0 border-b border-white/[0.06] bg-[#070a12]/80 backdrop-blur-xl">
          <div className="flex items-center gap-4 px-4 py-4 sm:px-6">
            <Link
              href="/workers"
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
            >
              <ArrowLeft className="size-4" /> All knowledge blocks
            </Link>
          </div>
          <div className="flex flex-wrap items-center gap-4 bg-gradient-to-r from-cyan-500/10 to-violet-500/[0.06] px-4 py-4 sm:px-6">
            <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-indigo-400 to-cyan-400 text-lg font-bold text-slate-950 shadow-lg shadow-cyan-500/20">
              In
            </span>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-bold text-white sm:text-2xl" style={{ fontFamily: "var(--font-display)" }}>
                {INVESTORS_BLOCK.name}
              </h1>
              <p className="text-sm text-slate-400">
                {INVESTORS_BLOCK.kind} · {INVESTORS_BLOCK.agents} agents
              </p>
            </div>
          </div>
          <nav aria-label="Knowledge block tabs" className="flex gap-1 overflow-x-auto px-3 sm:px-6">
            {TABS.map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                    active ? "border-cyan-400 text-white" : "border-transparent text-slate-400 hover:text-white",
                  )}
                >
                  <Icon className="size-3.5" />
                  {item.id}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="min-w-0 p-4 sm:p-6 lg:p-8">
          {tab === "Overview" && <InvestorsOverview />}
          {tab === "Analytics" && <InvestorsAnalytics agentId={linkedAgentId} />}
          {tab !== "Overview" && tab !== "Analytics" && (
            <ExistingWorkerTabBridge tab={tab} agentId={linkedAgentId} />
          )}
        </div>
      </div>
    </AppShell>
  );
}

function ExistingWorkerTabBridge({ tab, agentId }: { tab: Tab; agentId?: string }) {
  return (
    <div className="mx-auto max-w-2xl rounded-2xl border border-white/[0.06] bg-white/[0.015] p-6">
      <h2 className="text-lg font-semibold text-white">{tab}</h2>
      <p className="mt-2 text-sm text-slate-400">
        This tab stays as it works today on a worker screen. Agents in the Investors block are reached here.
      </p>
      <ul className="mt-4 space-y-2">
        {BLOCK_AGENTS.map((agent) => (
          <li key={agent.id} className="rounded-xl border border-white/[0.06] px-3 py-2.5 text-sm text-slate-300">
            <span className="font-medium text-white">{agent.name}</span>
            <span className="text-slate-500"> · {agent.role}</span>
          </li>
        ))}
      </ul>
      {agentId ? (
        <Link
          href={`/workers/${agentId}?tab=${tab}`}
          className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-cyan-500 px-4 text-sm font-semibold text-slate-950 hover:bg-cyan-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
        >
          Open {tab} on linked worker
        </Link>
      ) : (
        <Link
          href="/workers"
          className="mt-5 inline-flex min-h-11 items-center rounded-xl border border-white/10 px-4 text-sm text-slate-200 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        >
          Browse knowledge / workers
        </Link>
      )}
    </div>
  );
}
