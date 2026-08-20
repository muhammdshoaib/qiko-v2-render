"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, FileText, Link as LinkIcon, MessageSquare, RefreshCw, Search, SendHorizonal, ShieldAlert, Database } from "lucide-react";
import { Badge, Button, cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { SourcesTab } from "@/components/sources-tab";
import { DocumentsTab } from "@/components/documents-tab";
import { ResearchTab } from "@/components/research-tab";
import { WorkerAvatar } from "@/components/worker-avatar";
import {
  askIntelligence, getDiscrepancies, listAgents, listIntelligenceSources, type Discrepancy, type IntelligenceSource,
} from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

const BG = "#050810";

export default function IntelligenceWorkerPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = useMemo(() => agents.data?.find((a) => a.id === agentId), [agents.data, agentId]);

  const discrepancies = useQuery({
    queryKey: ["intelligence-discrepancies", agentId],
    queryFn: () => getDiscrepancies(agentId),
  });
  const sources = useQuery({
    queryKey: ["intelligence-sources", agentId],
    queryFn: () => listIntelligenceSources(agentId),
  });

  const byClass = useMemo(() => {
    const map = new Map<string, Discrepancy[]>();
    for (const d of discrepancies.data ?? []) {
      map.set(d.class, [...(map.get(d.class) ?? []), d]);
    }
    return map;
  }, [discrepancies.data]);

  const [tab, setTab] = useState<"discrepancies" | "chat" | "sources" | "documents" | "research">("discrepancies");

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

        {tab === "discrepancies" && (
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
                <ShieldAlert className="size-4 text-amber-400" /> Open discrepancies
              </h2>
              <button onClick={() => discrepancies.refetch()} className="text-white/50 hover:text-white">
                <RefreshCw className="size-4" />
              </button>
            </div>
            {discrepancies.isLoading && <PageSkeleton />}
            {!discrepancies.isLoading && (discrepancies.data?.length ?? 0) === 0 && (
              <EmptyState sources={sources.data ?? []} />
            )}
            {Array.from(byClass.entries()).map(([cls, items]) => (
              <div key={cls} className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-white/40">{cls.replace(/_/g, " ")}</p>
                {items.map((d, idx) => (
                  <DiscrepancyCard key={`${cls}-${idx}`} discrepancy={d} />
                ))}
              </div>
            ))}
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

function DiscrepancyCard({ discrepancy: d }: { discrepancy: Discrepancy }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 text-sm text-white/80">
      <div className="mb-2 flex items-start justify-between gap-2">
        <p className="font-medium text-white">{d.title}</p>
        {d.ref && <span className="shrink-0 rounded bg-white/[0.08] px-2 py-0.5 text-xs text-white/70">{d.ref}</span>}
      </div>
      <p className="mb-3 leading-relaxed text-white/60">{d.summary}</p>
      {d.sources.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {d.sources.map((s, i) => (
            s.url ? (
              <a key={i} href={s.url} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 rounded bg-white/[0.06] px-2 py-1 text-xs text-white/70 hover:bg-white/[0.10] hover:text-white">
                <LinkIcon className="size-3" /> {s.source}
              </a>
            ) : (
              <span key={i} className="inline-flex items-center gap-1 rounded bg-white/[0.06] px-2 py-1 text-xs text-white/70">
                {s.source}
              </span>
            )
          ))}
        </div>
      )}
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

function EmptyState({ sources }: { sources: IntelligenceSource[] }) {
  const connected = sources.filter((s) => s.connected).map((s) => s.name);
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-6 text-center">
      <div className="mx-auto mb-4 grid size-11 place-items-center rounded-xl bg-emerald-400/10 text-emerald-300">
        <Bot className="size-5" />
      </div>
      <p className="text-sm font-medium text-white">No open discrepancies</p>
      <p className="mt-1 text-xs text-white/50">
        Connected sources: {connected.length > 0 ? connected.join(", ") : "none"}.
        Add Slack, Qiko Track or GitHub to start surfacing claim-vs-evidence gaps.
      </p>
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
