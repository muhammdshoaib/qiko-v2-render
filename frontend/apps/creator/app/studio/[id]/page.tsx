"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, Download, MessageSquare, Search, SendHorizonal } from "lucide-react";
import { Badge, Button, Card, CardContent } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { ask, batchAnswer, batchExportUrl, listAgents, type BatchAnswer } from "@/lib/api";

const TABS = ["Chat", "Research"] as const;

export default function StudioWorkerPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Chat");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === id);

  return (
    <AppShell title="Studio">
      <div className="mx-auto max-w-4xl space-y-6">
        <button onClick={() => router.push("/studio")} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to Studio
        </button>

        <div className="flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-secondary text-white">
            <Bot className="size-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold">{worker?.name ?? "Worker"}</h1>
            <Badge variant="muted">Published</Badge>
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

        {tab === "Chat" && <StudioChat />}
        {tab === "Research" && <StudioResearch />}
      </div>
    </AppShell>
  );
}

function StudioChat() {
  const [cid] = useState(() => `studio-${Math.random().toString(36).slice(2)}`);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: (question: string) => ask(cid, question),
    onMutate: (question) => setMessages((m) => [...m, { role: "user", text: question }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply.text }]),
  });

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="min-h-40 space-y-3">
          {messages.length === 0 && <p className="text-sm text-muted-foreground">Ask this worker anything -- it answers grounded in its knowledge base.</p>}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"}`}>{m.text}</div>
            </div>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send.mutate(text); setText(""); } }} className="flex gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a question..."
            className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          <Button type="submit" size="icon" disabled={send.isPending}><SendHorizonal className="size-4" /></Button>
        </form>
      </CardContent>
    </Card>
  );
}

function StudioResearch() {
  const [raw, setRaw] = useState("");
  const questions = raw.split("\n").map((q) => q.trim()).filter(Boolean);
  const run = useMutation({ mutationFn: () => batchAnswer(questions) });
  const [exporting, setExporting] = useState(false);

  async function onExport() {
    setExporting(true);
    try {
      const url = await batchExportUrl(questions);
      const a = document.createElement("a");
      a.href = url; a.download = "studio-research.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card><CardContent className="space-y-3 pt-6">
        <p className="text-sm text-muted-foreground">
          <Search className="mr-1 inline size-3.5" />
          Feed this worker a research brief -- one topic/question per line. Each comes back grounded in its
          knowledge, with a confidence score and citations, ready to export.
        </p>
        <textarea value={raw} onChange={(e) => setRaw(e.target.value)}
          placeholder={"Does the company hold ISO 9001?\nWhat is our coverage in Region X?"}
          className="min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={!run.data || exporting} onClick={onExport}>
            <Download className="mr-1 size-4" /> {exporting ? "Exporting..." : "Export .xlsx"}
          </Button>
          <Button disabled={questions.length === 0 || run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? "Researching..." : `Research ${questions.length || ""} topic(s)`}
          </Button>
        </div>
      </CardContent></Card>

      {run.data?.map((a: BatchAnswer) => (
        <Card key={a.id}>
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
