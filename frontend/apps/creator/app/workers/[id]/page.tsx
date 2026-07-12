"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Bot, BrainCircuit, Calendar, Check, ChevronUp, CircleCheck, Code, Copy, ExternalLink, FileText,
  GraduationCap, Globe, Link2, ListChecks, MessageCircle, MessageSquare, Phone, SendHorizonal, Share2, Sparkles,
  Trash2, Users, Zap,
} from "lucide-react";
import { Badge, Button, Card, CardContent, Input, Label, Skeleton, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  addBehavior, addFaq, addPolicy, addWebsite, ask, batchAnswer, batchExportUrl,
  deleteDocument, getVapiCredentials, ingest, listAgents, listDocuments, listLeads, listRfpPacks,
  saveVapiCredentials, updateAgentConfig, updateCalendlyEventType, type Agent, type BatchAnswer, type Doc,
} from "@/lib/api";

const TABS = [
  { id: "Overview", icon: Sparkles, iconColor: "text-cyan-400" },
  { id: "Chat", icon: MessageSquare, iconColor: "text-slate-400" },
  { id: "Train", icon: GraduationCap, iconColor: "text-slate-400" },
  { id: "CRM", icon: Users, iconColor: "text-slate-400" },
  { id: "Connections", icon: Link2, iconColor: "text-slate-400" },
  { id: "Batch", icon: ListChecks, iconColor: "text-slate-400" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const AVATAR_GRADIENTS = [
  "from-cyan-500 to-blue-500", "from-violet-500 to-purple-600", "from-emerald-500 to-teal-500",
  "from-amber-500 to-orange-600", "from-pink-500 to-rose-500", "from-indigo-500 to-blue-600",
];
function avatarGradient(id: string): string {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_GRADIENTS[hash % AVATAR_GRADIENTS.length];
}

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className="min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />;
}

export default function WorkerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("Overview");
  const docs = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === id);
  const refresh = () => qc.invalidateQueries({ queryKey: ["documents"] });
  const refreshAgents = () => qc.invalidateQueries({ queryKey: ["agents"] });

  return (
    <AppShell title="Worker">
      <div className="flex h-full flex-col">
        <div className="relative border-b border-white/5 bg-[#0a0f1a]/80 backdrop-blur-xl">
          <div className="flex items-center gap-4 px-6 py-4">
            <Link href="/workers" className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
              <ArrowLeft className="size-4" /> All Workers
            </Link>
          </div>
          <div className="flex items-center gap-4 bg-gradient-to-r from-slate-800/30 to-slate-700/20 px-6 py-4">
            <div className={cn("flex size-14 shrink-0 items-center justify-center rounded-xl text-xl font-bold text-white shadow-lg bg-gradient-to-br", worker ? avatarGradient(worker.id) : "from-primary to-secondary")}>
              {worker?.name.charAt(0).toUpperCase() ?? "?"}
            </div>
            <div className="flex-1">
              <h1 className="text-xl font-bold text-white">{worker?.name ?? "Worker"}</h1>
              <p className="text-sm text-slate-400">{(worker?.config?.expertise as string) || "Worker"}</p>
            </div>
            {worker && (
              <Badge variant={worker.status === "ready" ? "success" : "muted"} dot={worker.status === "ready"} className="capitalize">
                {worker.status}
              </Badge>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3 px-4 py-3 sm:grid-cols-2 sm:px-6">
            <div className="relative rounded-xl p-3 sm:p-4 bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 border-2 border-emerald-500/50 shadow-lg shadow-emerald-500/10">
              <div className="flex items-center gap-2.5 sm:gap-3">
                <span className="grid size-9 sm:size-10 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-cyan-500">
                  <Zap className="size-4 sm:size-5 text-white" />
                </span>
                <div className="text-left min-w-0">
                  <div className="flex items-center gap-1.5 sm:gap-2">
                    <span className="font-semibold text-sm sm:text-base text-white">Qiko-Sonic</span>
                    <span className="px-1.5 py-0.5 rounded text-[9px] sm:text-[10px] font-medium bg-emerald-500/30 text-emerald-300 shrink-0">ACTIVE</span>
                  </div>
                  <p className="text-[11px] sm:text-xs text-slate-400">Instant · No setup</p>
                </div>
              </div>
              <div className="absolute top-2 right-2 size-2 rounded-full bg-emerald-400 animate-pulse" />
            </div>
            <div className="relative rounded-xl p-3 sm:p-4 bg-white/[0.01] opacity-70">
              <div className="flex items-center gap-2.5 sm:gap-3">
                <span className="grid size-9 sm:size-10 shrink-0 place-items-center rounded-lg bg-slate-700">
                  <BrainCircuit className="size-4 sm:size-5 text-white" />
                </span>
                <div className="text-left min-w-0">
                  <div className="flex items-center gap-1.5 sm:gap-2">
                    <span className="font-semibold text-sm sm:text-base text-slate-300">Custom</span>
                    <span className="text-[9px] sm:text-[10px] px-1 py-0.5 rounded bg-amber-500/20 text-amber-400 whitespace-nowrap">COMING SOON</span>
                  </div>
                  <p className="text-[11px] sm:text-xs text-slate-400">Fine-tuned · Your data</p>
                </div>
              </div>
            </div>
          </div>
          <div className="overflow-x-auto px-4 py-2 sm:px-6">
            <div className="flex w-max items-center gap-2">
              {TABS.map(({ id: t, icon: Icon, iconColor }) => (
                <button key={t} onClick={() => setTab(t)}
                  className={cn("inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3 text-sm font-medium transition-all duration-200 sm:px-4",
                    tab === t ? "bg-slate-800/80 text-white shadow-sm" : "text-slate-300 hover:bg-white/5 hover:text-white")}>
                  <Icon className={cn("size-4 shrink-0", tab === t ? iconColor : "text-slate-400")} />
                  <span className="leading-none">{t}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-6">
          {tab === "Overview" && <OverviewTab id={id} worker={worker} />}
          {tab === "Train" && (
            <TrainTab id={id} worker={worker} docs={docs.data} loading={docs.isLoading}
              onKnowledgeChange={refresh} onWorkerChange={refreshAgents} />
          )}
          {tab === "CRM" && <CrmTab />}
          {tab === "Connections" && <ConnectionsTab id={id} worker={worker} />}
          {tab === "Chat" && <ChatTab />}
          {tab === "Batch" && <BatchTab />}
        </div>
      </div>
    </AppShell>
  );
}

function OverviewTab({ id, worker }: { id: string; worker?: Agent }) {
  const packs = useQuery({ queryKey: ["rfp-packs", id], queryFn: () => listRfpPacks(id) });
  const [overviewOpen, setOverviewOpen] = useState(true);
  const [shareOpen, setShareOpen] = useState(true);
  const cfg = worker?.config ?? {};
  const expertise = (cfg.expertise as string) || "General purpose";
  const capabilities = [
    "Answers questions using your trained knowledge base",
    "Personality friendly tone and communication style",
    "Handles multiple conversations simultaneously",
    "Never forgets important details or context",
    "Available around the clock without breaks",
  ];
  // Computed from window.location, so it must only ever render post-mount -- computing it
  // during the initial render would make the server-rendered markup (empty origin) mismatch
  // the client's first paint and trigger a hydration error (React #418).
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  const chatLink = origin ? `${origin}/embed/${worker?.tenant ?? ""}/${id}` : "";
  const widgetSnippet = `<script src="${origin}/widget.js" data-worker-id="${id}"></script>`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your digital worker&apos;s capabilities and performance</p>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-700/50 bg-gradient-to-br from-[#6366F1]/10 via-slate-800/30 to-[#22D3EE]/10">
        <button onClick={() => setOverviewOpen((o) => !o)}
          className="flex w-full items-center justify-between px-4 py-4 text-left transition-colors hover:bg-slate-700/20">
          <div className="flex items-center gap-2 text-base font-semibold">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-[#6366F1] to-[#22D3EE]">
              <Bot className="size-4 text-white" />
            </span>
            AI Model Overview
            <Badge variant="success" className="ml-2 text-xs">Active</Badge>
          </div>
          <ChevronUp className={cn("size-4 shrink-0 text-muted-foreground transition-transform", !overviewOpen && "rotate-180")} />
        </button>
        {overviewOpen && (
          <div className="space-y-6 px-4 pb-4">
            <div className="flex items-start gap-4">
              <span className="grid size-16 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-[#6366F1] to-[#22D3EE] shadow-lg shadow-[#6366F1]/20">
                <BrainCircuit className="size-8 text-white" />
              </span>
              <div>
                <h3 className="text-lg font-bold text-white">{worker?.name ?? "Worker"}</h3>
                <p className="text-sm font-medium text-cyan-400">{expertise}</p>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">
                  This AI model has been trained to serve as {expertise.toLowerCase().startsWith("a") || expertise.toLowerCase().startsWith("e") ? "an" : "a"} {expertise}.
                  It delivers consistent, knowledgeable responses 24/7.
                </p>
              </div>
            </div>
            <div className="rounded-xl bg-slate-800/50 p-4">
              <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
                <MessageCircle className="size-4 text-cyan-400" /> Language Response Capabilities
              </h4>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {capabilities.map((c) => (
                  <div key={c} className="flex items-start gap-2">
                    <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-400" />
                    <span className="text-sm text-slate-300">{c}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-700/50 bg-slate-800/30">
        <button onClick={() => setShareOpen((o) => !o)}
          className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-slate-700/20">
          <div className="flex items-center gap-2 text-base font-semibold">
            <Share2 className="size-4 text-cyan-400" /> Share &amp; Embed
          </div>
          <ChevronUp className={cn("size-4 shrink-0 text-muted-foreground transition-transform", !shareOpen && "rotate-180")} />
        </button>
        {shareOpen && (
          <div className="grid grid-cols-1 gap-4 px-4 pb-4 lg:grid-cols-2">
            <div className="min-w-0 overflow-hidden rounded-xl bg-slate-700/30 p-4">
              <div className="mb-3 flex items-center gap-2">
                <span className="shrink-0 rounded-lg bg-emerald-500/20 p-1.5">
                  <Globe className="size-4 text-emerald-400" />
                </span>
                <div className="min-w-0">
                  <h4 className="text-sm font-semibold text-white">Public Chat Link</h4>
                  <p className="text-xs text-slate-400">Share this link to let anyone chat with your AI</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1 overflow-hidden rounded-lg border border-slate-600/50 bg-slate-800/80 px-3 py-2">
                  <p className="truncate font-mono text-sm text-cyan-400">{chatLink}</p>
                </div>
                <Button variant="outline" size="sm" className="h-8 shrink-0 border-slate-600 hover:bg-slate-700" onClick={() => navigator.clipboard.writeText(chatLink)}>
                  <Copy className="size-4" />
                </Button>
                <a href={chatLink} target="_blank" rel="noreferrer">
                  <Button variant="outline" size="sm" className="h-8 shrink-0 border-slate-600 hover:bg-slate-700">
                    <ExternalLink className="size-4" />
                  </Button>
                </a>
              </div>
            </div>
            <div className="min-w-0 overflow-hidden rounded-xl bg-slate-700/30 p-4">
              <div className="mb-3 flex items-center gap-2">
                <span className="shrink-0 rounded-lg bg-purple-500/20 p-1.5">
                  <Code className="size-4 text-purple-400" />
                </span>
                <div className="min-w-0">
                  <h4 className="text-sm font-semibold text-white">Website Widget</h4>
                  <p className="text-xs text-slate-400">Add this code to embed the chat on your website</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1 overflow-hidden rounded-lg border border-slate-600/50 bg-slate-800/80 px-3 py-2">
                  <p className="truncate font-mono text-xs text-purple-400">{widgetSnippet}</p>
                </div>
                <Button variant="outline" size="sm" className="h-8 shrink-0 border-slate-600 hover:bg-slate-700" onClick={() => navigator.clipboard.writeText(widgetSnippet)}>
                  <Copy className="size-4" />
                </Button>
              </div>
              <p className="mt-2 flex items-center gap-1 text-xs text-slate-500">
                <Sparkles className="size-3" /> Paste before the closing &lt;/body&gt; tag
              </p>
            </div>
          </div>
        )}
      </div>

      {(packs.data?.length ?? 0) > 0 && (
        <Card>
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">Tenders</p>
              <Badge variant="muted">{packs.data!.length} active</Badge>
            </div>
            {packs.data!.map((p) => (
              <Link key={p.id} href={`/workers/${id}/tenders/${p.id}`}
                className="flex items-center justify-between rounded-lg border border-border/60 p-3 text-sm hover:bg-muted/50">
                <div>
                  <p className="font-medium">{p.title}</p>
                  <p className="text-xs text-muted-foreground">{p.client_name || "No client set"} {p.deadline ? `· Due ${p.deadline}` : ""}</p>
                </div>
                <Badge variant="muted">{p.stage}</Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function CrmTab() {
  const leads = useQuery({ queryKey: ["leads"], queryFn: listLeads });
  return (
    <Card>
      <CardContent className="pt-6 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">Captured leads</p>
          <Badge variant="muted">{leads.data?.length ?? 0}</Badge>
        </div>
        {leads.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {leads.data?.map((l) => (
          <div key={l.id} className="flex items-center justify-between rounded-lg border border-border/60 p-3 text-sm">
            <div>
              <p className="font-medium">{l.name}</p>
              <p className="text-xs text-muted-foreground">{l.email}</p>
            </div>
            <Badge variant="muted">{l.kind}</Badge>
          </div>
        ))}
        {leads.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No leads captured yet -- they show up here as visitors submit an enterprise or RAG-wired form.</p>
        )}
      </CardContent>
    </Card>
  );
}

const CONNECTIONS_SUBTABS = ["Voice", "Calendly"] as const;

function ConnectionsTab({ id, worker }: { id: string; worker?: Agent }) {
  const [sub, setSub] = useState<(typeof CONNECTIONS_SUBTABS)[number]>("Voice");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {CONNECTIONS_SUBTABS.map((s) => (
          <button key={s} onClick={() => setSub(s)}
            className={cn("flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              sub === s ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}>
            {s === "Voice" ? <Phone className="size-3.5" /> : <Calendar className="size-3.5" />} {s}
          </button>
        ))}
      </div>
      {sub === "Voice" && <VoiceSubTab id={id} />}
      {sub === "Calendly" && <CalendlySubTab id={id} worker={worker} />}
    </div>
  );
}

function VoiceSubTab({ id }: { id: string }) {
  const creds = useQuery({ queryKey: ["vapi-credentials", id], queryFn: () => getVapiCredentials(id) });
  const [assistantId, setAssistantId] = useState("");
  const [publicKey, setPublicKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => saveVapiCredentials(id, { vapi_assistant_id: assistantId, vapi_public_key: publicKey, vapi_api_key: secretKey }),
    onSuccess: () => { setSecretKey(""); qc.invalidateQueries({ queryKey: ["vapi-credentials", id] }); },
  });

  return (
    <div className="space-y-4">
      <div>
        <p className="font-medium">Voice AI Settings</p>
        <p className="text-sm text-muted-foreground">Enable voice conversations so customers can call and talk to your digital worker</p>
      </div>

      {!creds.data?.vapi_credentials_added && (
        <Card className="border-amber-500/30 bg-amber-500/5"><CardContent className="space-y-2 pt-6 text-sm">
          <p className="font-medium">Vapi API Key Required</p>
          <p className="text-muted-foreground">You need these 3 values from your Vapi account to enable voice for this worker.</p>
          <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
            <li><b>Assistant ID</b> - In Vapi, go to Assistants {"\u2192"} open your assistant {"\u2192"} copy the Assistant ID (this is not the assistant name).</li>
            <li><b>Public Key</b> - In Vapi, go to Dashboard {"\u2192"} API Keys {"\u2192"} copy the Public Key (usually starts with pk-).</li>
            <li><b>Private Key</b> - In Vapi, go to Dashboard {"\u2192"} API Keys {"\u2192"} copy the Private Key (keep this private).</li>
          </ol>
          <a href="https://vapi.ai" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-amber-600 hover:underline">
            Get Vapi ID & Keys <ExternalLink className="size-3.5" />
          </a>
        </CardContent></Card>
      )}

      <Card><CardContent className="space-y-4 pt-6">
        <p className="text-sm">Voice Status: <span className="font-medium">{creds.data?.vapi_credentials_added ? "Voice is enabled for this worker" : "Voice is not enabled"}</span></p>
        <div className="space-y-1.5">
          <Label>Assistant ID</Label>
          <Input placeholder="e.g. your-vapi-assistant-id" value={assistantId || creds.data?.vapi_assistant_id || ""}
            onChange={(e) => setAssistantId(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>Public Key</Label>
          <Input placeholder="pk-..." value={publicKey || creds.data?.vapi_public_key || ""}
            onChange={(e) => setPublicKey(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>Secret Key</Label>
          <Input type="password" placeholder={creds.data?.vapi_api_key_masked || "sk-..."} value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)} />
        </div>
        <div className="flex justify-end">
          <Button disabled={!assistantId || !publicKey || !secretKey || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving..." : "Save"}
          </Button>
        </div>
      </CardContent></Card>
    </div>
  );
}

function CalendlySubTab({ id, worker }: { id: string; worker?: Agent }) {
  const savedEventType = worker?.config?.calendly_event_type as string | undefined;
  const [url, setUrl] = useState("");
  const save = useMutation({ mutationFn: () => updateCalendlyEventType(id, url) });

  return (
    <div className="space-y-4">
      <div>
        <p className="font-medium">Calendly</p>
        <p className="text-sm text-muted-foreground">Connect a Calendly event type so your worker can schedule meetings</p>
      </div>
      <Card><CardContent className="space-y-3 pt-6">
        {savedEventType ? (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm">
            <p className="font-medium">Selected Calendly event</p>
            <p className="font-mono text-xs text-muted-foreground">{savedEventType}</p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No Calendly event type connected yet.</p>
        )}
        <div className="space-y-1.5">
          <Label>Calendly event type URL</Label>
          <Input placeholder="https://calendly.com/you/30min" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <div className="flex justify-end">
          <Button disabled={!url || save.isPending} onClick={() => save.mutate()}>
            {savedEventType ? "Change Calendly event" : "Connect Calendly"}
          </Button>
        </div>
      </CardContent></Card>
    </div>
  );
}

const TRAIN_STEPS = ["Background", "Tone", "Behavior", "Knowledge"] as const;
type TrainStep = (typeof TRAIN_STEPS)[number];

function TrainTab({ id, worker, docs, loading, onKnowledgeChange, onWorkerChange }: {
  id: string; worker?: Agent; docs?: Doc[]; loading: boolean;
  onKnowledgeChange: () => void; onWorkerChange: () => void;
}) {
  const [step, setStep] = useState<TrainStep>("Background");
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <GraduationCap className="size-4" /> Train Your Worker
      </div>
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {TRAIN_STEPS.map((s) => (
          <button key={s} onClick={() => setStep(s)}
            className={cn("flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              step === s ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}>
            {s}
          </button>
        ))}
      </div>
      {step === "Background" && (
        <BackgroundStep key={worker ? "loaded" : "loading"} id={id} worker={worker} onSaved={onWorkerChange} />
      )}
      {step === "Tone" && (
        <ToneStep key={worker ? "loaded" : "loading"} id={id} worker={worker} onSaved={onWorkerChange} />
      )}
      {step === "Behavior" && <BehaviorStep id={id} />}
      {step === "Knowledge" && <KnowledgeStep id={id} docs={docs} loading={loading} onChange={onKnowledgeChange} />}
    </div>
  );
}

function BackgroundStep({ id, worker, onSaved }: { id: string; worker?: Agent; onSaved: () => void }) {
  const cfg = worker?.config ?? {};
  const [expertise, setExpertise] = useState((cfg.expertise as string) ?? "");
  const [audience, setAudience] = useState((cfg.target_audience as string) ?? "");
  const [goal, setGoal] = useState((cfg.main_goal as string) ?? "");
  const [unique, setUnique] = useState((cfg.what_makes_you_unique as string) ?? "");
  const save = useMutation({
    mutationFn: () => updateAgentConfig(id, {
      expertise, target_audience: audience, main_goal: goal, what_makes_you_unique: unique,
    }),
    onSuccess: onSaved,
  });
  return (
    <Card><CardContent className="space-y-4 pt-6">
      <div><p className="font-medium">Who is your AI?</p></div>
      <div className="space-y-1.5">
        <Label>Your Expertise</Label>
        <Input placeholder="e.g., RFP and Proposal Response Specialist for security services"
          value={expertise} onChange={(e) => setExpertise(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Target Audience</Label>
        <Input placeholder="e.g., IDG bid, pre-sales, proposal, operations, and management team"
          value={audience} onChange={(e) => setAudience(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Main Goal</Label>
        <Input placeholder="e.g., Help IDG review RFP documents, extract required sections and answer them"
          value={goal} onChange={(e) => setGoal(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>What makes you unique?</Label>
        <Textarea placeholder="e.g., Specialised in complex security tenders, compliance requirements..."
          value={unique} onChange={(e) => setUnique(e.target.value)} />
      </div>
      <div className="flex justify-end"><Button disabled={save.isPending} onClick={() => save.mutate()}>Save Background</Button></div>
    </CardContent></Card>
  );
}

const TONE_OPTIONS = [
  { value: "friendly", emoji: "\u{1F60A}", label: "Friendly", description: "Warm & approachable" },
  { value: "professional", emoji: "\u{1F4BC}", label: "Professional", description: "Formal & business-like" },
  { value: "casual", emoji: "\u{1F60E}", label: "Casual", description: "Relaxed & conversational" },
  { value: "expert", emoji: "\u{1F393}", label: "Expert", description: "Authoritative & confident" },
  { value: "empathetic", emoji: "\u{1F49A}", label: "Empathetic", description: "Understanding & caring" },
] as const;

function ToneStep({ id, worker, onSaved }: { id: string; worker?: Agent; onSaved: () => void }) {
  const [tone, setTone] = useState((worker?.config?.tone as string) ?? "");
  const save = useMutation({ mutationFn: (t: string) => updateAgentConfig(id, { tone: t }), onSuccess: onSaved });
  return (
    <Card><CardContent className="space-y-4 pt-6">
      <p className="font-medium">How should it sound?</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {TONE_OPTIONS.map((t) => (
          <button key={t.value} onClick={() => { setTone(t.value); save.mutate(t.value); }}
            className={cn("flex items-center gap-3 rounded-lg border p-3 text-left transition-colors",
              tone === t.value ? "border-primary bg-primary/5" : "border-border hover:border-primary/40")}>
            <span className="text-xl">{t.emoji}</span>
            <span>
              <span className="block text-sm font-medium">{t.label}</span>
              <span className="block text-xs text-muted-foreground">{t.description}</span>
            </span>
          </button>
        ))}
      </div>
    </CardContent></Card>
  );
}

function BehaviorStep({ id }: { id: string }) {
  return (
    <SourceForm title="Prompts & rules" onSubmit={(sid) => addBehavior(id, sid, val("behavior"))}
      fields={[["behavior", "Define a prompt, guardrail, or rule for this worker", true]]} onDone={() => {}} />
  );

  function val(name: string): string {
    return (document.getElementById(`f-${name}`) as HTMLTextAreaElement | null)?.value ?? "";
  }
}

const KNOWLEDGE_CARDS = [
  { key: "faqs", title: "FAQs", description: "Common questions and answers your AI should know" },
  { key: "websites", title: "Websites", description: "URLs your AI can reference for information" },
  { key: "documents", title: "Documents", description: "PDFs, docs, or text files with important info" },
  { key: "policies", title: "Policies", description: "Rules, terms, or guidelines your AI must follow" },
] as const;

function KnowledgeStep({ id, docs, loading, onChange }: { id: string; docs?: Doc[]; loading: boolean; onChange: () => void }) {
  const [open, setOpen] = useState<(typeof KNOWLEDGE_CARDS)[number]["key"] | null>(null);

  function val(name: string): string {
    return (document.getElementById(`f-${name}`) as HTMLInputElement | HTMLTextAreaElement | null)?.value ?? "";
  }

  return (
    <div className="space-y-3">
      <p className="font-medium">FAQs & docs</p>
      {KNOWLEDGE_CARDS.map((c) => (
        <Card key={c.key}>
          <CardContent className="flex items-center justify-between py-4">
            <button className="flex-1 text-left" onClick={() => setOpen(open === c.key ? null : c.key)}>
              <p className="text-sm font-medium">{c.title}</p>
              <p className="text-xs text-muted-foreground">{c.description}</p>
            </button>
            {c.key === "documents" && <Badge variant="muted">{docs?.length ?? 0}</Badge>}
          </CardContent>
          {open === c.key && (
            <CardContent className="border-t border-border pt-4">
              {c.key === "faqs" && (
                <SourceForm title="Add an FAQ" onSubmit={(sid) => addFaq(id, sid, val("q"), val("a"))}
                  fields={[["q", "Question", false], ["a", "Answer", true]]} onDone={onChange} />
              )}
              {c.key === "websites" && (
                <SourceForm title="Add a website" onSubmit={(sid) => addWebsite(id, sid, val("name"), val("url"), val("details"))}
                  fields={[["name", "Name", false], ["url", "URL", false], ["details", "Details", true]]} onDone={onChange} />
              )}
              {c.key === "documents" && <KnowledgeTab id={id} docs={docs} loading={loading} onChange={onChange} />}
              {c.key === "policies" && (
                <SourceForm title="Add a policy" onSubmit={(sid) => addPolicy(id, sid, val("title"), val("body"))}
                  fields={[["title", "Title", false], ["body", "Body", true]]} onDone={onChange} />
              )}
            </CardContent>
          )}
        </Card>
      ))}
    </div>
  );
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
