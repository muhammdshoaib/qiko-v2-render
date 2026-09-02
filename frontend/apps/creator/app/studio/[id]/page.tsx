"use client";

// Common worker boilerplate cockpit (atype="worker"): the domain-neutral capabilities every worker
// has over agentcore -- grounded Chat, batch Research, Knowledge. Verticals (pre_sales_writer,
// sales_intelligence, finance) are separate capability packs; this page redirects to them by atype.
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, Bot, BookOpen, Download, Link2, MessageSquare, Search, SendHorizonal, Sparkles,
} from "lucide-react";
import { Badge, Button, Card, CardContent } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import {
  ask, batchAnswer, batchExportUrl, listAgents, listDocuments, type BatchAnswer,
} from "@/lib/api";

const VERTICAL_ROUTES: Record<string, string> = {
  pre_sales_writer: "pre-sales",
  sales_intelligence: "sales-intelligence",
  finance: "finance",
  intelligence: "intelligence",
};

const TABS = ["Overview", "Chat", "Research"] as const;

export default function StudioWorkerPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === id);

  // Verticals have their own cockpits -- bounce there if this worker is one of them.
  const verticalRoute = worker ? VERTICAL_ROUTES[worker.atype] : undefined;
  useEffect(() => {
    if (verticalRoute) router.replace(`/studio/${id}/${verticalRoute}`);
  }, [verticalRoute, id, router]);
  if (verticalRoute) return null;

  return (
    <AppShell title="Studio">
      <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6 lg:px-12">
        <button onClick={() => router.push("/studio")} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to Studio
        </button>

        <div className="flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-secondary text-white">
            <Bot className="size-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold">{worker?.name ?? "Worker"}</h1>
            <div className="flex items-center gap-2">
              <Badge variant={worker?.status === "ready" ? "success" : "muted"}>
                {worker?.status === "ready" ? "Ready" : "Training"}
              </Badge>
              <span className="text-xs text-muted-foreground">AI Worker</span>
            </div>
          </div>
        </div>

        <div className="flex gap-1 border-b border-border">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium ${tab === t ? "border-b-2 border-primary text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {t}
            </button>
          ))}
        </div>

        {tab === "Overview" && (
          <WorkerOverview agentId={id} ready={worker?.status === "ready"}
            onOpenChat={() => setTab("Chat")} onOpenResearch={() => setTab("Research")}
            onOpenKnowledge={() => router.push(`/workers/${id}`)}
            onOpenConnections={() => router.push(`/workers/${id}?tab=Connections`)} />
        )}
        {tab === "Chat" && <StudioChat agentId={id} />}
        {tab === "Research" && <StudioResearch agentId={id} />}
      </div>
    </AppShell>
  );
}

type Capability = { title: string; description: string; icon: typeof MessageSquare; onClick: () => void };

function WorkerOverview({ agentId, ready, onOpenChat, onOpenResearch, onOpenKnowledge, onOpenConnections }: {
  agentId: string; ready: boolean; onOpenChat: () => void; onOpenResearch: () => void;
  onOpenKnowledge: () => void; onOpenConnections: () => void;
}) {
  const docs = useQuery({ queryKey: ["documents", agentId], queryFn: () => listDocuments(agentId) });
  const sources = docs.data?.length ?? 0;
  const chunks = docs.data?.reduce((n, d) => n + d.chunks, 0) ?? 0;

  const metrics = [
    { label: "Status", value: ready ? "Ready" : "Training" },
    { label: "Knowledge sources", value: String(sources) },
    { label: "Indexed chunks", value: String(chunks) },
    { label: "Grounding", value: "Critic + gate" },
  ];

  // Domain-neutral capabilities every worker has over agentcore. A vertical layers extra screens
  // on top of these; the base worker is immediately usable for any domain from here.
  const capabilities: Capability[] = [
    { title: "Chat", description: "Ask the worker anything -- answers grounded in its knowledge, with an anti-hallucination gate",
      icon: MessageSquare, onClick: onOpenChat },
    { title: "Research", description: "Batch-answer many questions at once with confidence scores, citations, and xlsx export",
      icon: Search, onClick: onOpenResearch },
    { title: "Knowledge", description: "Upload and manage the documents this worker reasons over",
      icon: BookOpen, onClick: onOpenKnowledge },
    { title: "Connections", description: "Wire the worker to voice, calendar, email, and messaging channels",
      icon: Link2, onClick: onOpenConnections },
  ];

  return (
    <div className="w-full space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {metrics.map((m) => (
          <Card key={m.label}><CardContent className="space-y-1 pt-6">
            <p className="text-xs text-muted-foreground">{m.label}</p>
            <p className="text-xl font-bold">{m.value}</p>
          </CardContent></Card>
        ))}
      </div>

      <div>
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-primary" /> What this worker can do
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {capabilities.map((c) => {
            const Icon = c.icon;
            return (
              <Card key={c.title} className="cursor-pointer transition-colors hover:border-primary/40" onClick={c.onClick}>
                <CardContent className="flex items-start gap-3 pt-6">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="size-4" />
                  </div>
                  <div className="flex-1 space-y-1">
                    <p className="text-sm font-medium">{c.title}</p>
                    <p className="text-xs text-muted-foreground">{c.description}</p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function StudioChat({ agentId }: { agentId: string }) {
  const [cid] = useState(() => `studio-${Math.random().toString(36).slice(2)}`);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: (question: string) => ask(cid, question, agentId),
    onMutate: (question) => setMessages((m) => [...m, { role: "user", text: question }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply.text }]),
    onError: () => setMessages((m) => [...m, { role: "assistant", text: "Sorry, I couldn't answer that just now. Please try again in a moment." }]),
  });

  return (
    <Card className="w-full">
      <CardContent className="flex min-h-[28rem] flex-col space-y-4 pt-6">
        <div className="min-h-40 flex-1 space-y-3">
          {messages.length === 0 && <p className="text-sm text-muted-foreground">Ask this worker anything -- it answers grounded in its knowledge base.</p>}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <ChatBubble role={m.role} text={m.text} />
            </div>
          ))}
          {send.isPending && <div className="flex justify-start"><TypingIndicator /></div>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send.mutate(text); setText(""); } }} className="flex w-full gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a question..." aria-label="Ask a question"
            className="min-w-0 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          <Button type="submit" size="icon" disabled={send.isPending} aria-label="Send message"><SendHorizonal className="size-4" /></Button>
        </form>
      </CardContent>
    </Card>
  );
}

function StudioResearch({ agentId }: { agentId: string }) {
  const [raw, setRaw] = useState("");
  const questions = raw.split("\n").map((q) => q.trim()).filter(Boolean);
  const run = useMutation({ mutationFn: () => batchAnswer(questions, agentId) });
  const [exporting, setExporting] = useState(false);

  async function onExport() {
    setExporting(true);
    try {
      const url = await batchExportUrl(questions, agentId);
      const a = document.createElement("a");
      a.href = url; a.download = "studio-research.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="w-full space-y-4">
      <Card className="w-full"><CardContent className="space-y-3 pt-6">
        <p className="text-sm text-muted-foreground">
          <Search className="mr-1 inline size-3.5" />
          Feed this worker a research brief -- one topic/question per line. Each comes back grounded in its
          knowledge, with a confidence score and citations, ready to export.
        </p>
        <textarea value={raw} onChange={(e) => setRaw(e.target.value)}
          placeholder={"What is our refund policy?\nWhich regions do we operate in?"}
          className="min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={!run.data || exporting} onClick={onExport}>
            <Download className="mr-1 size-4" /> {exporting ? "Exporting..." : "Export .xlsx"}
          </Button>
          <Button disabled={questions.length === 0 || run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? "Researching..." : `Research ${questions.length || ""} topic(s)`}
          </Button>
        </div>
        {run.isError && <p className="text-xs text-red-500">Couldn&apos;t research those topics - please try again.</p>}
        {run.isSuccess && run.data.length === 0 && <p className="text-xs text-muted-foreground">No answers were returned.</p>}
      </CardContent></Card>

      {run.data?.map((a: BatchAnswer) => (
        <Card key={a.id} className="w-full">
          <CardContent className="space-y-2 pt-6">
            <div className="flex items-start justify-between gap-3">
              <p className="flex items-center gap-2 font-medium"><MessageSquare className="size-4 text-primary" />{a.question}</p>
              <Badge variant={a.decision === "auto_accept" ? "success" : "muted"}>
                {a.decision === "auto_accept" ? "High confidence" : "Needs review"} · {(a.confidence * 100).toFixed(0)}%
              </Badge>
            </div>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{a.answer}</p>
            {a.citations.length > 0 && <p className="text-xs text-muted-foreground">{a.citations.length} source(s) from the knowledge base.</p>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
