"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, BarChart3, Bot, BrainCircuit, ChevronUp, CircleCheck, Database, GraduationCap,
  Link2, Lock, MessageCircle, MessageSquare, Settings, Sparkles, Users, Zap, type LucideIcon,
} from "lucide-react";
import { Badge, Card, CardContent, Skeleton, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { WorkerAvatar } from "@/components/worker-avatar";
import { SourcesTab } from "@/components/sources-tab";
import {
  WorkerChatTab,
  WorkerConnectionsTab,
  WorkerCrmTab,
  WorkerSettingsTab,
  WorkerTrainTab,
} from "@/components/worker-cockpit-tabs";
import { getAgentAnalytics, listAgents, listDocuments, me, type Agent } from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

type Tab = "Overview" | "Analytics" | "Chat" | "Train" | "Sources" | "CRM" | "Connections" | "Settings";
const TABS: { id: Tab; icon: LucideIcon; locked?: boolean }[] = [
  { id: "Overview", icon: Sparkles },
  { id: "Analytics", icon: BarChart3 },
  { id: "Chat", icon: MessageSquare },
  { id: "Train", icon: GraduationCap },
  { id: "Sources", icon: Database },
  { id: "CRM", icon: Users },
  { id: "Connections", icon: Link2 },
  { id: "Settings", icon: Settings },
];

export default function WorkerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(TABS.some((t) => t.id === initialTab && !t.locked) ? (initialTab as Tab) : "Overview");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === id);
  // Viewer role is read-only: management tabs (Train/Connections/Settings) are locked so a viewer
  // cannot edit knowledge, connections or config. Backend already enforces these (require_role
  // editor); this hides/blocks the actions client-side too (QIK-307). Overview + Chat stay viewable.
  const account = useQuery({ queryKey: ["me"], queryFn: me });
  const isViewer = account.data?.role === "viewer";
  const MANAGE_TABS: Tab[] = ["Train", "Sources", "Connections", "Settings"];
  const tabLocked = (t: Tab) => !!TABS.find((x) => x.id === t)?.locked || (isViewer && MANAGE_TABS.includes(t));
  useEffect(() => {
    if (isViewer && MANAGE_TABS.includes(tab)) setTab("Overview");
  }, [isViewer, tab]);
  const docs = useQuery({ queryKey: ["documents", id], queryFn: () => listDocuments(id), enabled: !!worker });
  const refresh = () => qc.invalidateQueries({ queryKey: ["documents", id] });
  const refreshAgents = () => qc.invalidateQueries({ queryKey: ["agents"] });

  if (agents.isLoading) {
    return <AppShell title="Worker"><p className="p-6 text-sm text-slate-400">Checking worker availability...</p></AppShell>;
  }
  if (agents.isError) {
    return (
      <AppShell title="Worker">
        <div className="p-6 text-sm text-slate-600">
          Couldn&apos;t verify this worker. <button className="text-indigo-600 underline" onClick={() => agents.refetch()}>Retry</button>
        </div>
      </AppShell>
    );
  }
  if (!worker) {
    return (
      <AppShell title="Worker unavailable">
        <div className="mx-auto max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold text-foreground">Worker unavailable</h1>
          <p className="mt-2 text-sm text-slate-400">Return to Workers and choose an available worker.</p>
          <Link href="/workers" className="mt-4 inline-flex min-h-11 items-center rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white">Back to Workers</Link>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Worker">
      <div className="flex min-w-0 flex-col overflow-x-hidden">
        <div className="relative min-w-0 border-b border-border bg-card/95 backdrop-blur-xl">
          <div className="flex items-center gap-4 px-4 py-4 sm:px-6">
            <Link href="/workers" className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm text-slate-400 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
              <ArrowLeft className="size-4" /> All knowledge blocks
            </Link>
          </div>
          <div className="flex flex-wrap items-center gap-4 bg-gradient-to-r from-indigo-50 to-violet-50 px-4 py-4 sm:px-6">
            <WorkerAvatar name={worker?.name} size="lg" ready={worker?.status === "ready"} />
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-xl font-bold text-foreground">{worker?.name ?? "Worker"}</h1>
              <p className="truncate text-sm text-slate-400">{workerTypeLabel(worker?.atype)}</p>
            </div>
            {worker && (
              <Badge variant={worker.status === "ready" ? "success" : "muted"} dot={worker.status === "ready"} className="capitalize">
                {worker.status}
              </Badge>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3 px-4 py-3 sm:grid-cols-2 sm:px-6">
            <div className="relative rounded-xl border border-emerald-200 bg-emerald-500/[0.06] p-3 sm:p-4">
              <div className="flex items-center gap-2.5 sm:gap-3">
                <span className="grid size-9 sm:size-10 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500">
                  <Zap className="size-4 sm:size-5 text-white" />
                </span>
                <div className="text-left min-w-0">
                  <div className="flex items-center gap-1.5 sm:gap-2">
                    <span className="font-semibold text-sm sm:text-base text-foreground">Qiko-Sonic</span>
                    <span className="shrink-0 whitespace-nowrap rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">ACTIVE</span>
                  </div>
                  <p className="text-[11px] sm:text-xs text-slate-400">Instant · No setup</p>
                </div>
              </div>
              <div className="absolute top-2 right-2 size-2 rounded-full bg-emerald-400" />
            </div>
            <div className="relative rounded-xl bg-slate-50 p-3 opacity-70 sm:p-4">
              <div className="flex items-center gap-2.5 sm:gap-3">
                <span className="grid size-9 sm:size-10 shrink-0 place-items-center rounded-lg bg-slate-200">
                  <BrainCircuit className="size-4 sm:size-5 text-slate-500" />
                </span>
                <div className="text-left min-w-0">
                  <div className="flex items-center gap-1.5 sm:gap-2">
                    <span className="font-semibold text-sm sm:text-base text-slate-600">Custom</span>
                    <span className="shrink-0 whitespace-nowrap rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">COMING SOON</span>
                  </div>
                  <p className="text-[11px] sm:text-xs text-slate-400">Fine-tuned · Your data</p>
                </div>
              </div>
            </div>
          </div>
          <nav aria-label="Worker sections" className="max-w-full overflow-x-auto px-4 py-2 sm:px-6">
            <div className="flex w-max min-w-full items-center gap-2 pr-4 sm:pr-0">
              {TABS.map(({ id: t, icon: Icon }) => {
                if (tabLocked(t)) {
                  return (
                    <button key={t} type="button" disabled aria-disabled="true" title={isViewer && MANAGE_TABS.includes(t) ? "View-only role" : "Locked"}
                      className="inline-flex h-10 shrink-0 cursor-not-allowed items-center gap-2 whitespace-nowrap rounded-xl border border-transparent px-3 text-sm font-medium text-slate-500 opacity-60 sm:px-4">
                      <Icon className="size-4 shrink-0 text-slate-600" />
                      <span className="leading-none">{t}</span>
                      <Lock className="size-3.5 shrink-0 text-slate-500" />
                    </button>
                  );
                }
                const isActive = tab === t;
                return (
                  <button key={t} type="button" onClick={() => setTab(t)} aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 sm:px-4",
                      isActive
                        ? "border-indigo-200 bg-indigo-50 text-indigo-700 shadow-sm"
                        : "border-transparent text-slate-500 hover:bg-muted hover:text-foreground",
                    )}>
                    <Icon className={cn("size-4 shrink-0", isActive ? "text-indigo-600" : "text-slate-500")} />
                    <span className="leading-none">{t}</span>
                  </button>
                );
              })}
            </div>
          </nav>
        </div>

        <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-4 sm:p-6">
          {tab === "Overview" && <OverviewTab id={id} worker={worker} />}
          {tab === "Analytics" && <AnalyticsTab id={id} />}
          {tab === "Train" && !isViewer && (
            <WorkerTrainTab id={id} worker={worker} docs={docs.data} loading={docs.isLoading}
              onKnowledgeChange={refresh} onWorkerChange={refreshAgents} />
          )}
          {tab === "Sources" && !isViewer && <SourcesTab agentId={id} />}
          {tab === "CRM" && <WorkerCrmTab id={id} readOnly={isViewer} />}
          {tab === "Connections" && !isViewer && <WorkerConnectionsTab id={id} worker={worker} />}
          {tab === "Chat" && <WorkerChatTab id={id} worker={worker} />}
          {tab === "Settings" && !isViewer && (
            <WorkerSettingsTab key={worker ? "loaded" : "loading"} id={id} worker={worker} onWorkerChange={refreshAgents} />
          )}
        </div>
      </div>
    </AppShell>
  );
}

function OverviewTab({ id, worker }: { id: string; worker?: Agent }) {
  const [overviewOpen, setOverviewOpen] = useState(true);
  const typeLabel = workerTypeLabel(worker?.atype);
  const capabilities = [
    "Answers questions using your trained knowledge base",
    "Personality friendly tone and communication style",
    "Handles multiple conversations simultaneously",
    "Never forgets important details or context",
    "Available around the clock without breaks",
  ];
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-foreground sm:text-2xl">Dashboard</h1>
        <p className="text-sm text-muted-foreground sm:text-base">Overview of your digital worker&apos;s capabilities and performance</p>
      </div>

      <div className="min-w-0 overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-indigo-50 via-white to-violet-500/10">
        <button onClick={() => setOverviewOpen((o) => !o)}
          className="flex w-full items-start justify-between gap-3 px-4 py-4 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-base font-semibold">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600">
              <Bot className="size-4 text-white" />
            </span>
            <span className="text-foreground">AI Model Overview</span>
            <Badge variant="success" className="text-xs">Active</Badge>
          </div>
          <ChevronUp className={cn("mt-1 size-4 shrink-0 text-muted-foreground transition-transform", !overviewOpen && "rotate-180")} />
        </button>
        {overviewOpen && (
          <div className="space-y-6 px-4 pb-4">
            <div className="flex min-w-0 items-start gap-4">
              <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-200 sm:size-16">
                <BrainCircuit className="size-7 text-white sm:size-8" />
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-lg font-bold text-foreground">{worker?.name ?? "Worker"}</h3>
                <p className="text-sm font-medium text-indigo-600">{typeLabel}</p>
                <p className="mt-2 break-words text-sm leading-relaxed text-slate-400">
                  This {typeLabel} delivers consistent, knowledgeable responses 24/7, grounded in the
                  knowledge you&apos;ve trained it on.
                </p>
              </div>
            </div>
            <div className="rounded-xl bg-muted p-4">
              <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <MessageCircle className="size-4 text-indigo-600" /> Language Response Capabilities
              </h4>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {capabilities.map((c) => (
                  <div key={c} className="flex items-start gap-2">
                    <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-700" />
                    <span className="text-sm text-slate-600">{c}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Usage volume for this worker -- calls and tokens, deliberately not cost. Cost stays admin-only
// (see AgentUsageStats on the backend); this is the view every tenant role, including a viewer,
// should always be able to see for their own worker.
const ANALYTICS_STATS: { key: "calls" | "input_tokens" | "output_tokens" | "unpriced_calls"; label: string }[] = [
  { key: "calls", label: "Total calls" },
  { key: "input_tokens", label: "Input tokens" },
  { key: "output_tokens", label: "Output tokens" },
  { key: "unpriced_calls", label: "Calls pending pricing data" },
];

function AnalyticsTab({ id }: { id: string }) {
  const analytics = useQuery({ queryKey: ["agent-analytics", id], queryFn: () => getAgentAnalytics(id) });
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-foreground sm:text-2xl">Analytics</h1>
        <p className="text-sm text-muted-foreground sm:text-base">Usage volume for this worker -- calls and tokens, not cost.</p>
      </div>
      {analytics.isError && (
        <div className="text-sm text-slate-600">
          Couldn&apos;t load usage analytics. <button className="text-indigo-600 underline" onClick={() => analytics.refetch()}>Retry</button>
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {ANALYTICS_STATS.map((s) => (
          <Card key={s.key}><CardContent className="space-y-1 pt-6">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{s.label}</p>
            {analytics.isLoading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <p className="text-2xl font-bold text-foreground">{(analytics.data?.[s.key] ?? 0).toLocaleString()}</p>
            )}
          </CardContent></Card>
        ))}
      </div>
    </div>
  );
}
