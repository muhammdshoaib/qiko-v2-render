"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
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
import { InvestorsChat } from "@/components/knowledge/investors-chat";
import { InvestorsOverview } from "@/components/knowledge/investors-overview";
import { BLOCK_AGENTS, INVESTORS_BLOCK } from "@/components/knowledge/investors-data";
import { ObservabilityTab } from "@/components/intelligence-layer/support-tabs";
import { mergeActivity } from "@/components/intelligence-layer/feed";
import { SourcesTab } from "@/components/sources-tab";
import { useBrain } from "@/lib/brain/store";
import { listAgents, listDocuments, me, type Agent, type Doc } from "@/lib/api";
import {
  WorkerConnectionsTab,
  WorkerCrmTab,
  WorkerSettingsTab,
  WorkerTrainTab,
} from "@/app/workers/[id]/page";

type Tab = "Overview" | "Observability" | "Analytics" | "Chat" | "Train" | "Sources" | "CRM" | "Connections" | "Settings";

const TABS: { id: Tab; icon: LucideIcon }[] = [
  { id: "Overview", icon: Sparkles },
  { id: "Observability", icon: Activity },
  { id: "Analytics", icon: BarChart3 },
  { id: "Chat", icon: MessageSquare },
  { id: "Train", icon: GraduationCap },
  { id: "Sources", icon: Database },
  { id: "CRM", icon: Users },
  { id: "Connections", icon: Link2 },
  { id: "Settings", icon: Settings },
];

const MANAGE_TABS: Tab[] = ["Train", "Sources", "Connections", "Settings"];

export default function InvestorsKnowledgePage() {
  const [tab, setTab] = useState<Tab>("Overview");
  const qc = useQueryClient();
  const brain = useBrain();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const account = useQuery({ queryKey: ["me"], queryFn: me });
  const isViewer = account.data?.role === "viewer";
  const observabilityFeed = useMemo(() => mergeActivity(brain.events), [brain.events]);

  const linkedAgent = useMemo(() => {
    const list = agents.data ?? [];
    const match = list.find((agent) => /intent|intelligence|investor/i.test(`${agent.name} ${agent.atype}`));
    return match ?? list[0];
  }, [agents.data]);

  const linkedAgentId = linkedAgent?.id;
  const docs = useQuery({
    queryKey: ["documents", linkedAgentId],
    queryFn: () => listDocuments(linkedAgentId!),
    enabled: !!linkedAgentId && (tab === "Train"),
  });

  const tabLocked = (t: Tab) => isViewer && MANAGE_TABS.includes(t);

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
                {linkedAgent ? ` · linked ${linkedAgent.name}` : ""}
              </p>
            </div>
          </div>
          <nav aria-label="Knowledge block tabs" className="flex gap-1 overflow-x-auto px-3 sm:px-6">
            {TABS.map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              const locked = tabLocked(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={locked}
                  onClick={() => {
                    if (!locked) setTab(item.id);
                  }}
                  aria-current={active ? "page" : undefined}
                  title={locked ? "View-only role" : undefined}
                  className={cn(
                    "flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                    locked && "cursor-not-allowed opacity-50",
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
          {tab === "Observability" && (
            <ObservabilityTab
              events={observabilityFeed}
              onInspect={() => setTab("Overview")}
            />
          )}
          {tab === "Analytics" && <InvestorsAnalytics agentId={linkedAgentId} />}
          {tab === "Chat" && (
            <InvestorsChat agents={agents.data ?? []} agentsLoading={agents.isLoading} />
          )}
          {tab !== "Overview" && tab !== "Observability" && tab !== "Analytics" && tab !== "Chat" && (
            <ExistingWorkerTabBridge
              tab={tab}
              agentId={linkedAgentId}
              worker={linkedAgent}
              docs={docs.data}
              docsLoading={docs.isLoading}
              agentsLoading={agents.isLoading}
              agentsError={agents.isError}
              onRetryAgents={() => agents.refetch()}
              onKnowledgeChange={() => qc.invalidateQueries({ queryKey: ["documents", linkedAgentId] })}
              onWorkerChange={() => qc.invalidateQueries({ queryKey: ["agents"] })}
            />
          )}
        </div>
      </div>
    </AppShell>
  );
}

function ExistingWorkerTabBridge({
  tab,
  agentId,
  worker,
  docs,
  docsLoading,
  agentsLoading,
  agentsError,
  onRetryAgents,
  onKnowledgeChange,
  onWorkerChange,
}: {
  tab: Tab;
  agentId?: string;
  worker?: Agent;
  docs?: Doc[];
  docsLoading: boolean;
  agentsLoading: boolean;
  agentsError: boolean;
  onRetryAgents: () => void;
  onKnowledgeChange: () => void;
  onWorkerChange: () => void;
}) {
  if (agentsLoading) {
    return <p className="text-sm text-slate-400">Loading worker screens…</p>;
  }

  if (agentsError) {
    return (
      <div className="rounded-2xl border border-white/[0.08] bg-[#0b0f18] p-6 text-sm text-slate-300">
        Couldn&apos;t load linked workers.{" "}
        <button type="button" className="text-cyan-300 underline" onClick={onRetryAgents}>
          Retry
        </button>
      </div>
    );
  }

  if (!agentId || !worker) {
    return (
      <div className="mx-auto max-w-2xl rounded-2xl border border-white/[0.08] bg-[#0b0f18] p-6">
        <h2 className="text-lg font-semibold text-white">{tab}</h2>
        <p className="mt-2 text-sm text-slate-400">
          Link or create a worker for this knowledge block to use the same {tab} screen as Qiko Workers.
        </p>
        <ul className="mt-4 space-y-2">
          {BLOCK_AGENTS.map((agent) => (
            <li key={agent.id} className="rounded-xl border border-white/[0.06] px-3 py-2.5 text-sm text-slate-300">
              <span className="font-medium text-white">{agent.name}</span>
              <span className="text-slate-500"> · {agent.role}</span>
            </li>
          ))}
        </ul>
        <Link
          href="/workers"
          className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-cyan-500 px-4 text-sm font-semibold text-slate-950 hover:bg-cyan-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
        >
          Open Knowledge / workers
        </Link>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
        <p className="text-[12.5px] text-slate-400">
          Showing the existing worker <span className="font-medium text-slate-200">{tab}</span> UI for{" "}
          <span className="font-medium text-white">{worker.name}</span>
        </p>
        <Link
          href={`/workers/${agentId}?tab=${tab}`}
          className="text-[12px] font-medium text-cyan-300 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        >
          Open full worker screen
        </Link>
      </div>

      {tab === "Train" && (
        <WorkerTrainTab
          id={agentId}
          worker={worker}
          docs={docs}
          loading={docsLoading}
          onKnowledgeChange={onKnowledgeChange}
          onWorkerChange={onWorkerChange}
        />
      )}
      {tab === "Sources" && <SourcesTab agentId={agentId} />}
      {tab === "CRM" && <WorkerCrmTab id={agentId} />}
      {tab === "Connections" && <WorkerConnectionsTab id={agentId} worker={worker} />}
      {tab === "Settings" && (
        <WorkerSettingsTab key={worker ? "loaded" : "loading"} id={agentId} worker={worker} onWorkerChange={onWorkerChange} />
      )}
    </div>
  );
}
