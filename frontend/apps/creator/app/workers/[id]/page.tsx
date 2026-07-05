"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, FileText, SendHorizonal, Trash2 } from "lucide-react";
import { Badge, Button, Card, CardContent, Input, Label, Skeleton, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  addBehavior, addFaq, addPolicy, addWebsite, ask, batchAnswer, batchExportUrl,
  deleteDocument, ingest, listAgents, listDocuments, type BatchAnswer, type Doc,
} from "@/lib/api";

const TABS = ["Knowledge", "Behaviors", "FAQs", "Websites", "Policies", "Chat", "Batch"] as const;
type Tab = (typeof TABS)[number];

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className="min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />;
}

export default function WorkerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("Knowledge");
  const docs = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === id);
  const refresh = () => qc.invalidateQueries({ queryKey: ["documents"] });

  return (
    <AppShell title="Worker">
      <div className="mx-auto max-w-3xl space-y-6">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to workers
        </Link>

        <div className="flex items-center gap-3">
          <span className="grid size-12 place-items-center rounded-xl bg-gradient-to-br from-primary to-secondary text-primary-foreground">
            <Bot className="size-6" />
          </span>
          <div>
            <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>{worker?.name ?? "Worker"}</h1>
            {worker && <Badge variant={worker.status === "ready" ? "success" : "muted"}>{worker.status}</Badge>}
          </div>
        </div>

        <div className="flex gap-1 border-b border-border overflow-x-auto">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={cn("shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {t}
            </button>
          ))}
        </div>

        {tab === "Knowledge" && <KnowledgeTab id={id} docs={docs.data} loading={docs.isLoading} onChange={refresh} />}
        {tab === "Behaviors" && (
          <SourceForm title="Add a behavior" onSubmit={(sid) => addBehavior(id, sid, val("behavior"))} fields={[["behavior", "Behavior", true]]} onDone={refresh} />
        )}
        {tab === "FAQs" && (
          <SourceForm title="Add an FAQ" onSubmit={(sid) => addFaq(id, sid, val("q"), val("a"))} fields={[["q", "Question", false], ["a", "Answer", true]]} onDone={refresh} />
        )}
        {tab === "Websites" && (
          <SourceForm title="Add a website" onSubmit={(sid) => addWebsite(id, sid, val("name"), val("url"), val("details"))} fields={[["name", "Name", false], ["url", "URL", false], ["details", "Details", true]]} onDone={refresh} />
        )}
        {tab === "Policies" && (
          <SourceForm title="Add a policy" onSubmit={(sid) => addPolicy(id, sid, val("title"), val("body"))} fields={[["title", "Title", false], ["body", "Body", true]]} onDone={refresh} />
        )}
        {tab === "Chat" && <ChatTab />}
        {tab === "Batch" && <BatchTab />}
      </div>
    </AppShell>
  );

  // simple field-value store scoped per render via DOM ids
  function val(name: string): string {
    return (document.getElementById(`f-${name}`) as HTMLInputElement | HTMLTextAreaElement | null)?.value ?? "";
  }
}

function ChatTab() {
  const [conversationId] = useState(() => `test-${Date.now()}`);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [busy, setBusy] = useState(false);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input) return;
    const q = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const reply = await ask(conversationId, q);
      setMessages((m) => [...m, reply]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <p className="text-sm text-muted-foreground">Test how this worker answers, grounded in the knowledge you&apos;ve added.</p>
        <div className="min-h-40 space-y-2 rounded-md border border-border p-3">
          {messages.length === 0 && <p className="text-sm text-muted-foreground">Ask a question to see a grounded reply…</p>}
          {messages.map((m, i) => (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <span className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-sm",
                m.role === "user" ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-muted rounded-bl-sm")}>
                {m.text}
              </span>
            </div>
          ))}
        </div>
        <form onSubmit={send} className="flex gap-2">
          <Input placeholder="Ask your worker something…" value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
          <Button type="submit" disabled={busy || !input}><SendHorizonal className="size-4" /></Button>
        </form>
      </CardContent>
    </Card>
  );
}

function BatchTab() {
  const [raw, setRaw] = useState("");
  const questions = raw.split("\n").map((q) => q.trim()).filter(Boolean);
  const run = useMutation({ mutationFn: () => batchAnswer(questions) });
  const [exporting, setExporting] = useState(false);

  async function onExport() {
    setExporting(true);
    try {
      const url = await batchExportUrl(questions);
      const a = document.createElement("a");
      a.href = url;
      a.download = "worker-answers.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card><CardContent className="space-y-3 pt-6">
        <p className="text-sm text-muted-foreground">Paste one question per line (e.g. RFP requirements). Each gets a grounded answer, a confidence score, and a decision — high-confidence answers auto-accept, the rest are flagged for human review.</p>
        <Textarea placeholder={"Does the company hold ISO 9001?\nWhat services are offered in Region X?"} value={raw} onChange={(e) => setRaw(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={!run.data || exporting} onClick={onExport}>
            {exporting ? "Exporting…" : "Download .xlsx"}
          </Button>
          <Button disabled={questions.length === 0 || run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? "Answering…" : `Run ${questions.length || ""} question(s)`}
          </Button>
        </div>
      </CardContent></Card>

      {run.data?.map((a: BatchAnswer) => (
        <Card key={a.id}>
          <CardContent className="space-y-2 pt-6">
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium">{a.question}</p>
              <Badge variant={a.decision === "auto_accept" ? "success" : "muted"}>
                {a.decision === "auto_accept" ? "Auto-accepted" : "Needs review"} · {(a.confidence * 100).toFixed(0)}%
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{a.answer}</p>
            {a.citations.length > 0 && (
              <p className="text-xs text-muted-foreground">{a.citations.length} supporting citation(s) from your knowledge base.</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function KnowledgeTab({ id, docs, loading, onChange }: { id: string; docs?: Doc[]; loading: boolean; onChange: () => void }) {
  const [text, setText] = useState("");
  const add = useMutation({ mutationFn: () => ingest(`${id}-${Date.now()}`, text), onSuccess: () => { setText(""); onChange(); } });
  const remove = useMutation({ mutationFn: (d: string) => deleteDocument(d), onSuccess: onChange });
  return (
    <div className="space-y-4">
      <Card><CardContent className="space-y-3 pt-6">
        <Textarea id="f-knowledge" placeholder="Add free-text knowledge…" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="flex justify-end"><Button disabled={!text.trim() || add.isPending} onClick={() => add.mutate()}>Add knowledge</Button></div>
      </CardContent></Card>
      <div className="space-y-2">
        {loading && [0, 1].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        {docs?.map((d) => (
          <Card key={d.doc_id}><CardContent className="flex items-center justify-between py-3">
            <div className="flex items-center gap-3"><FileText className="size-4 text-muted-foreground" />
              <span className="text-sm font-medium">{d.doc_id}</span><Badge variant="muted">{d.chunks}</Badge></div>
            <Button variant="ghost" size="icon" onClick={() => remove.mutate(d.doc_id)}><Trash2 className="size-4 text-muted-foreground" /></Button>
          </CardContent></Card>
        ))}
        {docs?.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No documents yet.</p>}
      </div>
    </div>
  );
}

function SourceForm({ title, fields, onSubmit, onDone }: {
  title: string;
  fields: [string, string, boolean][];
  onSubmit: (sourceId: string) => Promise<unknown>;
  onDone: () => void;
}) {
  const m = useMutation({ mutationFn: () => onSubmit(`${Date.now()}`), onSuccess: onDone });
  return (
    <Card><CardContent className="space-y-3 pt-6">
      <p className="font-medium">{title}</p>
      {fields.map(([name, label, area]) => (
        <div key={name} className="space-y-1.5">
          <Label htmlFor={`f-${name}`}>{label}</Label>
          {area ? <Textarea id={`f-${name}`} /> : <Input id={`f-${name}`} />}
        </div>
      ))}
      {m.isError && <p className="text-sm text-destructive">Not permitted (needs editor role).</p>}
      {m.isSuccess && <p className="text-sm text-success">Added — grounding updated.</p>}
      <div className="flex justify-end"><Button disabled={m.isPending} onClick={() => m.mutate()}>Save</Button></div>
    </CardContent></Card>
  );
}
