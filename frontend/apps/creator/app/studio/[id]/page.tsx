"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, Bot, CheckCircle2, ClipboardCheck, Download, FileText, ListChecks,
  Lock, MessageSquare, Search, SendHorizonal, Shield, TrendingUp, Users,
} from "lucide-react";
import { Badge, Button, Card, CardContent } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import {
  ask, batchAnswer, batchExportUrl, getPackStats, listAgents, listDocuments, listRfpPacks,
  type BatchAnswer, type RfpPack,
} from "@/lib/api";

const TABS = ["Overview", "Chat", "Research", "Win/Loss"] as const;

export default function StudioWorkerPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === id);

  // The Sales Intelligence worker has its own dedicated cockpit (own top bar, left nav, chat
  // panel) rather than this generic RFP-pack tab layout -- bounce there if landed on directly.
  useEffect(() => {
    if (worker?.atype === "sales_intelligence") router.replace(`/studio/${id}/sales-intelligence`);
  }, [worker?.atype, id, router]);
  if (worker?.atype === "sales_intelligence") return null;

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

        {tab === "Overview" && (
          <StudioOverview agentId={id} onOpenResearch={() => setTab("Research")}
            onOpenWinLoss={() => setTab("Win/Loss")} onOpenKnowledge={() => router.push(`/workers/${id}`)}
            onOpenConnections={() => router.push(`/workers/${id}?tab=Connections`)} />
        )}
        {tab === "Chat" && <StudioChat />}
        {tab === "Research" && <StudioResearch />}
        {tab === "Win/Loss" && <StudioWinLoss agentId={id} />}
      </div>
    </AppShell>
  );
}

type UseCase = { title: string; description: string; icon: typeof FileText; status: "active" | "coming_soon"; onClick?: () => void };

function StudioOverview({ agentId, onOpenResearch, onOpenWinLoss, onOpenKnowledge, onOpenConnections }: {
  agentId: string; onOpenResearch: () => void; onOpenWinLoss: () => void; onOpenKnowledge: () => void; onOpenConnections: () => void;
}) {
  const router = useRouter();
  const packs = useQuery({ queryKey: ["rfp-packs", agentId], queryFn: () => listRfpPacks(agentId) });
  const docs = useQuery({ queryKey: ["documents"], queryFn: listDocuments });

  function openCompliance() {
    // Compliance Checker lives inside a specific tender's cockpit (it checks THAT tender's
    // mandatory requirements) -- jump into the most recently created pack, or ask for one first.
    const target = packs.data?.[0];
    if (!target) {
      onOpenResearch();
      return;
    }
    router.push(`/workers/${agentId}/tenders/${target.id}?tab=Compliance`);
  }

  const activeBids = packs.data?.length ?? 0;
  const inReview = packs.data?.filter((p: RfpPack) => p.stage === "review" || p.stage === "final").length ?? 0;
  const avgReadiness = activeBids > 0 ? Math.round((inReview / activeBids) * 100) : 0;
  const dataVolume = docs.data?.reduce((n, d) => n + d.chunks, 0) ?? 0;
  const nextDeadline = packs.data?.map((p) => p.deadline).filter(Boolean).sort()[0] ?? null;

  const metrics = [
    { label: "Active Bids", value: String(activeBids) },
    { label: "Avg Readiness", value: activeBids > 0 ? `${avgReadiness}%` : "\u2014" },
    { label: "Data volume", value: `${dataVolume} chunks` },
    { label: "Next Bid", value: nextDeadline ?? "\u2014" },
  ];

  const useCases: UseCase[] = [
    { title: "AI Response Generation", description: "Generate section-by-section RFP responses from the knowledge base",
      icon: FileText, status: "active", onClick: onOpenResearch },
    { title: "Knowledge Base", description: "Manage and search your response library",
      icon: ClipboardCheck, status: "active", onClick: onOpenKnowledge },
    { title: "Section Assignment", description: "Assign and track section ownership across the team",
      icon: ListChecks, status: "active" },
    { title: "Compliance Checker", description: "Validate responses against compliance requirements",
      icon: Shield, status: "active", onClick: openCompliance },
    { title: "Win/Loss Analysis", description: "Track outcomes and improve future responses",
      icon: TrendingUp, status: "active", onClick: onOpenWinLoss },
    { title: "Teams Integration", description: "Notifications and collaboration via Microsoft Teams",
      icon: Users, status: "active", onClick: onOpenConnections },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {metrics.map((m) => (
          <Card key={m.label}><CardContent className="space-y-1 pt-6">
            <p className="text-xs text-muted-foreground">{m.label}</p>
            <p className="text-xl font-bold">{m.value}</p>
          </CardContent></Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {useCases.map((uc) => {
          const Icon = uc.icon;
          const clickable = uc.status === "active" && uc.onClick;
          return (
            <Card key={uc.title} className={uc.status === "coming_soon" ? "opacity-60" : clickable ? "cursor-pointer transition-colors hover:border-primary/40" : ""}
              {...(clickable ? { onClick: uc.onClick } : {})}>
              <CardContent className="flex items-start gap-3 pt-6">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  {uc.status === "coming_soon" ? <Lock className="size-4" /> : <Icon className="size-4" />}
                </div>
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{uc.title}</p>
                    {uc.status === "coming_soon"
                      ? <Badge variant="muted">Coming soon</Badge>
                      : <CheckCircle2 className="size-3.5 text-emerald-500" />}
                  </div>
                  <p className="text-xs text-muted-foreground">{uc.description}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
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
              <ChatBubble role={m.role} text={m.text} />
            </div>
          ))}
          {send.isPending && <div className="flex justify-start"><TypingIndicator /></div>}
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

const LOSS_REASON_LABELS: Record<string, string> = {
  price: "Price", technical: "Technical fit", relationship: "Relationship", timeline: "Timeline",
  no_bid_decision: "No-bid decision", other: "Other", unspecified: "Unspecified",
};

function StudioWinLoss({ agentId }: { agentId: string }) {
  const stats = useQuery({ queryKey: ["pack-stats", agentId], queryFn: () => getPackStats(agentId) });
  const s = stats.data;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        <TrendingUp className="mr-1 inline size-3.5" />
        Outcomes are recorded from the worker&apos;s Tenders list (mark a tender Won/Lost) -- this rolls them up.
      </p>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card><CardContent className="space-y-1 pt-6">
          <p className="text-xs text-muted-foreground">Win rate</p>
          <p className="text-xl font-bold">{s?.win_rate != null ? `${Math.round(s.win_rate * 100)}%` : "\u2014"}</p>
        </CardContent></Card>
        <Card><CardContent className="space-y-1 pt-6">
          <p className="text-xs text-muted-foreground">Won / Lost</p>
          <p className="text-xl font-bold">{s?.won ?? 0} / {s?.lost ?? 0}</p>
        </CardContent></Card>
        <Card><CardContent className="space-y-1 pt-6">
          <p className="text-xs text-muted-foreground">Pipeline value won</p>
          <p className="text-xl font-bold">${(s?.won_value ?? 0).toLocaleString()}</p>
        </CardContent></Card>
        <Card><CardContent className="space-y-1 pt-6">
          <p className="text-xs text-muted-foreground">Pending decision</p>
          <p className="text-xl font-bold">{s?.pending ?? 0}</p>
        </CardContent></Card>
      </div>

      <Card><CardContent className="space-y-3 pt-6">
        <p className="text-sm font-semibold">Why we lose</p>
        {s && Object.keys(s.loss_reasons).length > 0 ? (
          Object.entries(s.loss_reasons).sort((a, b) => b[1] - a[1]).map(([reason, count]) => (
            <div key={reason} className="flex items-center justify-between text-sm">
              <span>{LOSS_REASON_LABELS[reason] ?? reason}</span>
              <Badge variant="muted">{count}</Badge>
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">No lost tenders recorded yet.</p>
        )}
      </CardContent></Card>
    </div>
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
