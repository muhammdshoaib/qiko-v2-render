"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, FileText, MessageSquare, RefreshCw, Search, SendHorizonal, ShieldAlert, Database, Users } from "lucide-react";
import { Badge, Button, cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { SourcesTab } from "@/components/sources-tab";
import { DocumentsTab } from "@/components/documents-tab";
import { ResearchTab } from "@/components/research-tab";
import { WorkerAvatar } from "@/components/worker-avatar";
import { DiscrepanciesTab } from "./discrepancies-tab";
import { OverviewTab } from "./overview-tab";
import {
  askIntelligence, getIntelligenceMetrics, listAgents, listIntelligenceSources, type IntelligenceMetrics, type ProjectMetrics,
} from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

const BG = "#050810";

export default function IntelligenceWorkerPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = useMemo(() => agents.data?.find((a) => a.id === agentId), [agents.data, agentId]);

  const sources = useQuery({
    queryKey: ["intelligence-sources", agentId],
    queryFn: () => listIntelligenceSources(agentId),
  });
  const metrics = useQuery({
    queryKey: ["intelligence-metrics", agentId],
    queryFn: () => getIntelligenceMetrics(agentId),
  });

  const [tab, setTab] = useState<"overview" | "discrepancies" | "chat" | "sources" | "documents" | "research">("discrepancies");

  if (agents.isLoading) return <PageSkeleton />;
  if (!worker) return <UnavailableState onBack={() => router.push("/studio")} />;

  return (
    <div className="flex min-h-screen flex-col" style={{ background: BG }}>
      <header className="border-b border-white/[0.06] px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-6xl items-center gap-3">
          <button onClick={() => router.push("/studio")} className="text-white/50 hover:text-white">
            <ArrowLeft className="size-5" />
          </button>
          <WorkerAvatar name={worker.name} ready={worker.status === "ready"} size="md" />
          <div className="flex-1">
            <h1 className="text-base font-semibold text-white">{worker.name}</h1>
            <p className="text-xs text-white/50">{workerTypeLabel(worker.atype)}</p>
          </div>
          <Badge variant={worker.status === "ready" ? "success" : "muted"}>
            {worker.status === "ready" ? "Ready" : "Training"}
          </Badge>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">
        <div className="mb-4 border-b border-white/[0.08]">
          <nav className="flex gap-6" aria-label="Intelligence tabs">
            {([
              { key: "overview", label: "Overview", icon: Users },
              { key: "discrepancies", label: "Discrepancies", icon: ShieldAlert },
              { key: "chat", label: "Chat", icon: MessageSquare },
              { key: "sources", label: "Sources", icon: Database },
              { key: "documents", label: "Documents", icon: FileText },
              { key: "research", label: "Research", icon: Search },
            ] as const).map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={cn(
                  "flex items-center gap-2 border-b-2 px-1 pb-3 text-sm font-medium transition-colors",
                  tab === key
                    ? "border-primary text-white"
                    : "border-transparent text-white/50 hover:text-white"
                )}
              >
                <Icon className="size-4" /> {label}
              </button>
            ))}
          </nav>
        </div>

        {tab === "overview" && (
          <section className="text-white">
            <OverviewTab agentId={agentId} />
          </section>
        )}

        {tab === "discrepancies" && (
          <section className="space-y-4">
            <MetricsPanel metrics={metrics.data} loading={metrics.isLoading} onRefetch={() => metrics.refetch()} />
            <DiscrepanciesTab agentId={agentId} worker={worker} metrics={metrics.data} />
          </section>
        )}

        {tab === "chat" && (
          <section className="flex flex-col gap-4 lg:max-w-2xl">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
              <MessageSquare className="size-4 text-primary" /> Ask the worker
            </h2>
            <IntelligenceChat agentId={agentId} />
          </section>
        )}

        {tab === "sources" && (
          <section className="text-white">
            <SourcesTab agentId={agentId} />
          </section>
        )}

        {tab === "documents" && (
          <section className="text-white">
            <DocumentsTab agentId={agentId} />
          </section>
        )}

        {tab === "research" && (
          <section className="text-white">
            <ResearchTab agentId={agentId} />
          </section>
        )}
      </main>
    </div>
  );
}

function IntelligenceChat({ agentId }: { agentId: string }) {
  const [cid] = useState(() => `intelligence-${Math.random().toString(36).slice(2)}`);
  const [messages, setMessages] = useState<{ role: string; text: string; sources?: string[] }[]>([]);
  const [text, setText] = useState("");

  const send = useMutation({
    mutationFn: (question: string) => askIntelligence(cid, question, agentId),
    onMutate: (question) => setMessages((m) => [...m, { role: "user", text: question }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply.reply, sources: reply.sources }]),
    onError: () => setMessages((m) => [...m, { role: "assistant", text: "Sorry, I couldn't answer that just now. Please try again." }]),
  });

  return (
    <div className="flex flex-1 flex-col rounded-xl border border-white/[0.08] bg-white/[0.03]">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-white/50">Ask about open items, blocked tickets, or claims without evidence.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className="max-w-[85%]">
              <ChatBubble role={m.role} text={m.text} />
              {m.sources && m.sources.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-2">
                  {m.sources.map((url, j) => (
                    <a key={j} href={url} target="_blank" rel="noreferrer"
                      className="text-xs text-white/40 underline hover:text-white">
                      source {j + 1}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {send.isPending && <div className="flex justify-start"><TypingIndicator /></div>}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send.mutate(text); setText(""); } }}
        className="flex gap-2 border-t border-white/[0.08] p-3">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a question..."
          aria-label="Ask a question"
          className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/40 outline-none focus:border-indigo-400/45" />
        <Button type="submit" size="icon" disabled={send.isPending} aria-label="Send message">
          <SendHorizonal className="size-4" />
        </Button>
      </form>
    </div>
  );
}

function MetricsPanel({ metrics, loading, onRefetch }: { metrics: IntelligenceMetrics | undefined; loading: boolean; onRefetch: () => void }) {
  const keys = metrics ? Object.keys(metrics.projects) : [];
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 text-white">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
          <BarChart3 className="size-4 text-primary" /> Delivery metrics
        </h2>
        <button onClick={onRefetch} className="text-white/50 hover:text-white" aria-label="Refresh metrics">
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
        </button>
      </div>
      {loading && !metrics && <PageSkeleton />}
      {!loading && keys.length === 0 && (
        <p className="text-sm text-white/50">Connect Qiko Track to see delivery metrics.</p>
      )}
      {metrics && keys.length > 0 && (
        <div className="space-y-4">
          {keys.map((key) => {
            const project = metrics.projects[key];
            if (!project || project.available === false) {
              return (
                <div key={key} className="text-sm text-white/70">
                  <span className="font-medium text-white">{key}</span>: {project?.error ?? "metrics unavailable"}
                </div>
              );
            }
            const dist = (d: ProjectMetrics["cycleTime"]["hours"]) =>
              d ? `${d.count} samples, median ${d.medianHours}h, p85 ${d.p85Hours}h` : "no samples";
            const sprint = project.sprint;
            return (
              <div key={key} className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-white">{key}</span>
                  <span className="text-xs text-white/40">window {project.window.key}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Metric label="Throughput" value={`${project.throughput.tickets} tickets (${project.throughput.points} pts)`} />
                  <Metric label="WIP" value={`${project.wip.total} (${project.wip.blocked} blocked)`} />
                  <Metric label="Review queue" value={`${project.review.openCount} open${project.review.oldestOpen ? `, oldest ${Math.round(project.review.oldestOpen.hours)}h` : ""}`} />
                  <Metric label="Blocked spells" value={`${project.blocked.openSpells}${project.blocked.oldestOpenHours ? `, oldest ${Math.round(project.blocked.oldestOpenHours)}h` : ""}`} />
                  <Metric label="Cycle time" value={dist(project.cycleTime.hours)} />
                  <Metric label="Lead time" value={dist(project.leadTime.hours)} />
                  <Metric label="Deploys" value={`${project.leadTime.deploys}${project.leadTime.deploysPerWeek ? ` (${project.leadTime.deploysPerWeek}/wk)` : ""}`} />
                  {sprint && (
                    <Metric
                      label="Sprint"
                      value={`${sprint.done.tickets} of ${sprint.committed.tickets} done, ${sprint.projectedCarryOver.tickets} carry-over`}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/[0.04] p-2">
      <p className="text-xs text-white/40">{label}</p>
      <p className="text-sm font-medium text-white">{value}</p>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl bg-white/[0.05]" />
      ))}
    </div>
  );
}

function UnavailableState({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: BG }}>
      <div className="w-full max-w-sm rounded-2xl border border-white/[0.08] p-6 text-center">
        <p className="text-white">Worker unavailable</p>
        <Button className="mt-4 w-full" onClick={onBack}>Back to Studio</Button>
      </div>
    </div>
  );
}
