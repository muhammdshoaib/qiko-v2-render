"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, Bot, BrainCircuit, Calendar, ChevronDown, ChevronUp, CircleCheck,
  Database, ExternalLink, FileText, GraduationCap, HelpCircle, Library, Link2, Loader2, Lock, MessageCircle,
  MessageSquare, Phone, Plus, Search, SendHorizonal, Settings, Share2, Sparkles, Trash2, Upload, Users, Zap,
  type LucideIcon,
} from "lucide-react";
import { Badge, Button, Card, CardContent, Input, Label, Skeleton, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { WorkerAvatar } from "@/components/worker-avatar";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { CrmPipeline } from "@/components/crm-pipeline";
import {
  addFaq, addPolicy, addWebsite, ask, connectTeamsWebhook,
  deleteDocument, disconnectSalesforce, disconnectTeamsWebhook, getSalesforceCredentials,
  getTeamsWebhookStatus, getVapiCredentials, ingest, ingestFile, listAgents, listDocuments, markReady,
  saveSalesforceCredentials, saveVapiCredentials, testSalesforceConnection, testTeamsWebhook,
  updateAgentConfig, updateCalendlyEventType, type Agent, type Doc,
} from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

type Tab = "Overview" | "Chat" | "Train" | "CRM" | "Connections" | "Settings";
const TABS: { id: Tab; icon: LucideIcon; locked?: boolean }[] = [
  { id: "Overview", icon: Sparkles },
  { id: "Chat", icon: MessageSquare },
  { id: "Train", icon: GraduationCap },
  { id: "CRM", icon: Users, locked: true },
  { id: "Connections", icon: Link2 },
  { id: "Settings", icon: Settings },
];

function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn("min-h-24 w-full rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-200 placeholder:text-slate-500 transition-colors focus-visible:border-cyan-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500", className)} />;
}

export default function WorkerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(TABS.some((t) => t.id === initialTab && !t.locked) ? (initialTab as Tab) : "Overview");
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === id);
  const docs = useQuery({ queryKey: ["documents", id], queryFn: () => listDocuments(id), enabled: !!worker });
  const refresh = () => qc.invalidateQueries({ queryKey: ["documents", id] });
  const refreshAgents = () => qc.invalidateQueries({ queryKey: ["agents"] });

  if (agents.isLoading) {
    return <AppShell title="Worker"><p className="p-6 text-sm text-slate-400">Checking worker availability...</p></AppShell>;
  }
  if (agents.isError) {
    return (
      <AppShell title="Worker">
        <div className="p-6 text-sm text-slate-300">
          Couldn&apos;t verify this worker. <button className="text-cyan-300 underline" onClick={() => agents.refetch()}>Retry</button>
        </div>
      </AppShell>
    );
  }
  if (!worker) {
    return (
      <AppShell title="Worker unavailable">
        <div className="mx-auto max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold text-white">Worker unavailable</h1>
          <p className="mt-2 text-sm text-slate-400">Return to Workers and choose an available worker.</p>
          <Link href="/workers" className="mt-4 inline-flex min-h-11 items-center rounded-lg bg-cyan-500 px-4 text-sm font-semibold text-slate-950">Back to Workers</Link>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Worker">
      <div className="flex h-full flex-col">
        <div className="relative border-b border-white/[0.06] bg-[#070a12]/80 backdrop-blur-xl">
          <div className="flex items-center gap-4 px-6 py-4">
            <Link href="/workers" className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500">
              <ArrowLeft className="size-4" /> All Workers
            </Link>
          </div>
          <div className="flex items-center gap-4 bg-gradient-to-r from-cyan-500/10 to-violet-500/[0.06] px-6 py-4">
            <WorkerAvatar name={worker?.name} size="lg" ready={worker?.status === "ready"} />
            <div className="flex-1">
              <h1 className="text-xl font-bold text-white">{worker?.name ?? "Worker"}</h1>
              <p className="text-sm text-slate-400">{workerTypeLabel(worker?.atype)}</p>
            </div>
            {worker && (
              <Badge variant={worker.status === "ready" ? "success" : "muted"} dot={worker.status === "ready"} className="capitalize">
                {worker.status}
              </Badge>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3 px-4 py-3 sm:grid-cols-2 sm:px-6">
            <div className="relative rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] p-3 sm:p-4">
              <div className="flex items-center gap-2.5 sm:gap-3">
                <span className="grid size-9 sm:size-10 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-cyan-500">
                  <Zap className="size-4 sm:size-5 text-white" />
                </span>
                <div className="text-left min-w-0">
                  <div className="flex items-center gap-1.5 sm:gap-2">
                    <span className="font-semibold text-sm sm:text-base text-white">Qiko-Sonic</span>
                    <span className="shrink-0 whitespace-nowrap rounded border border-emerald-500/25 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400">ACTIVE</span>
                  </div>
                  <p className="text-[11px] sm:text-xs text-slate-400">Instant · No setup</p>
                </div>
              </div>
              <div className="absolute top-2 right-2 size-2 rounded-full bg-emerald-400" />
            </div>
            <div className="relative rounded-xl bg-white/[0.01] p-3 opacity-70 sm:p-4">
              <div className="flex items-center gap-2.5 sm:gap-3">
                <span className="grid size-9 sm:size-10 shrink-0 place-items-center rounded-lg bg-slate-700">
                  <BrainCircuit className="size-4 sm:size-5 text-white" />
                </span>
                <div className="text-left min-w-0">
                  <div className="flex items-center gap-1.5 sm:gap-2">
                    <span className="font-semibold text-sm sm:text-base text-slate-300">Custom</span>
                    <span className="shrink-0 whitespace-nowrap rounded border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">COMING SOON</span>
                  </div>
                  <p className="text-[11px] sm:text-xs text-slate-400">Fine-tuned · Your data</p>
                </div>
              </div>
            </div>
          </div>
          <nav aria-label="Worker sections" className="overflow-x-auto px-4 py-2 sm:px-6">
            <div className="flex w-max items-center gap-2">
              {TABS.map(({ id: t, icon: Icon, locked }) => {
                if (locked) {
                  return (
                    <button key={t} type="button" disabled aria-disabled="true" title="Locked"
                      className="inline-flex h-10 shrink-0 cursor-not-allowed items-center gap-2 whitespace-nowrap rounded-xl border border-transparent px-3 text-sm font-medium text-slate-500 opacity-60 sm:px-4">
                      <Icon className="size-4 shrink-0 text-slate-600" />
                      <span className="leading-none">{t}</span>
                      <Lock className="size-3.5 shrink-0 text-slate-500" />
                    </button>
                  );
                }
                const isActive = tab === t;
                return (
                  <button key={t} onClick={() => setTab(t)} aria-current={isActive ? "page" : undefined}
                    className={cn("inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border px-3 text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 sm:px-4",
                      isActive ? "border-cyan-500/30 bg-cyan-500/10 text-white" : "border-transparent text-slate-300 hover:bg-white/[0.04] hover:text-white")}>
                    <Icon className={cn("size-4 shrink-0", isActive ? "text-cyan-400" : "text-slate-500")} />
                    <span className="leading-none">{t}</span>
                  </button>
                );
              })}
            </div>
          </nav>
        </div>

        <div className="flex-1 overflow-auto p-6">
          {tab === "Overview" && <OverviewTab id={id} worker={worker} />}
          {tab === "Train" && (
            <TrainTab id={id} worker={worker} docs={docs.data} loading={docs.isLoading}
              onKnowledgeChange={refresh} onWorkerChange={refreshAgents} />
          )}
          {tab === "CRM" && <CrmTab id={id} />}
          {tab === "Connections" && <ConnectionsTab id={id} worker={worker} />}
          {tab === "Chat" && <ChatTab id={id} worker={worker} />}
          {tab === "Settings" && (
            <SettingsTab key={worker ? "loaded" : "loading"} id={id} worker={worker} onWorkerChange={refreshAgents} />
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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your digital worker&apos;s capabilities and performance</p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-gradient-to-br from-cyan-500/10 via-white/[0.015] to-violet-500/10">
        <button onClick={() => setOverviewOpen((o) => !o)}
          className="flex w-full items-center justify-between px-4 py-4 text-left transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500">
          <div className="flex items-center gap-2 text-base font-semibold">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-cyan-400 to-blue-500">
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
              <span className="grid size-16 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-cyan-400 to-blue-500 shadow-lg shadow-cyan-500/20">
                <BrainCircuit className="size-8 text-white" />
              </span>
              <div>
                <h3 className="text-lg font-bold text-white">{worker?.name ?? "Worker"}</h3>
                <p className="text-sm font-medium text-cyan-400">{typeLabel}</p>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">
                  This {typeLabel} delivers consistent, knowledgeable responses 24/7, grounded in the
                  knowledge you&apos;ve trained it on.
                </p>
              </div>
            </div>
            <div className="rounded-xl bg-white/[0.03] p-4">
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
    </div>
  );
}

function CrmTab({ id }: { id: string }) {
  return (
    <div className="h-[70vh]">
      <CrmPipeline agentId={id} />
    </div>
  );
}

const CONNECTIONS_SUBTABS = ["Voice", "Calendly", "Teams", "Salesforce"] as const;

function ConnectionsTab({ id, worker }: { id: string; worker?: Agent }) {
  const [sub, setSub] = useState<(typeof CONNECTIONS_SUBTABS)[number]>("Voice");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {CONNECTIONS_SUBTABS.map((s) => (
          <button key={s} onClick={() => setSub(s)}
            className={cn("flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
              sub === s ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}>
            {s === "Voice" ? <Phone className="size-3.5" /> : s === "Calendly" ? <Calendar className="size-3.5" /> : s === "Teams" ? <Users className="size-3.5" /> : <Share2 className="size-3.5" />} {s}
          </button>
        ))}
      </div>
      {sub === "Voice" && <VoiceSubTab id={id} />}
      {sub === "Calendly" && <CalendlySubTab id={id} worker={worker} />}
      {sub === "Teams" && <TeamsSubTab id={id} />}
      {sub === "Salesforce" && <SalesforceSubTab id={id} />}
    </div>
  );
}

function SalesforceSubTab({ id }: { id: string }) {
  const qc = useQueryClient();
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [instanceUrl, setInstanceUrl] = useState("");
  const [testResult, setTestResult] = useState<"idle" | "ok" | "error">("idle");
  const creds = useQuery({ queryKey: ["salesforce-credentials", id], queryFn: () => getSalesforceCredentials(id) });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["salesforce-credentials", id] });
  const save = useMutation({
    mutationFn: () => saveSalesforceCredentials(id, { client_id: clientId, client_secret: clientSecret, instance_url: instanceUrl }),
    onSuccess: () => { setClientSecret(""); invalidate(); },
  });
  const disconnect = useMutation({ mutationFn: () => disconnectSalesforce(id), onSuccess: invalidate });
  const test = useMutation({
    mutationFn: () => testSalesforceConnection(id),
    onSuccess: () => setTestResult("ok"),
    onError: () => setTestResult("error"),
  });

  return (
    <div className="space-y-4">
      <div>
        <p className="font-medium">Salesforce</p>
        <p className="text-sm text-muted-foreground">Sync this worker&apos;s CRM pipeline contacts to Salesforce as Leads.</p>
      </div>

      {!creds.data?.salesforce_credentials_added && (
        <Card className="border-amber-500/30 bg-amber-500/5"><CardContent className="space-y-2 pt-6 text-sm">
          <p className="font-medium">Connected App required</p>
          <p className="text-muted-foreground">Create a Connected App in your Salesforce org with the Client Credentials OAuth flow enabled, then paste its details here. This is the same connection for every worker -- nothing here is specific to one client.</p>
          <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>Salesforce Setup {"\u2192"} App Manager {"\u2192"} New Connected App.</li>
            <li>Enable OAuth Settings, add the <b>Client Credentials Flow</b>, and run as an integration user.</li>
            <li>Copy the Consumer Key (Client ID) and Consumer Secret (Client Secret).</li>
          </ol>
        </CardContent></Card>
      )}

      <Card><CardContent className="space-y-4 pt-6">
        <p className="text-sm">Status: <span className="font-medium">{creds.data?.salesforce_credentials_added ? `Connected to ${creds.data.instance_url}` : "Not connected"}</span></p>
        {creds.data?.salesforce_credentials_added ? (
          <div className="flex items-center gap-2">
            <Button variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? "Testing..." : "Test connection"}
            </Button>
            <Button variant="outline" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
              Disconnect
            </Button>
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="sf-instance-url">Instance URL</Label>
              <Input id="sf-instance-url" placeholder="https://yourorg.my.salesforce.com" value={instanceUrl} onChange={(e) => setInstanceUrl(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sf-client-id">Client ID (Consumer Key)</Label>
              <Input id="sf-client-id" value={clientId} onChange={(e) => setClientId(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sf-client-secret">Client Secret (Consumer Secret)</Label>
              <Input id="sf-client-secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} />
            </div>
            <div className="flex justify-end">
              <Button disabled={!clientId || !clientSecret || !instanceUrl || save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? "Connecting..." : "Connect"}
              </Button>
            </div>
          </>
        )}
        {testResult === "ok" && <p className="text-xs text-emerald-600">Connection works.</p>}
        {testResult === "error" && <p className="text-xs text-red-500">Couldn&apos;t authenticate with Salesforce -- check the client id/secret and instance URL.</p>}
      </CardContent></Card>
    </div>
  );
}

function TeamsSubTab({ id }: { id: string }) {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [testResult, setTestResult] = useState<"idle" | "ok" | "error">("idle");
  const status = useQuery({ queryKey: ["teams-webhook"], queryFn: getTeamsWebhookStatus });
  const connect = useMutation({
    mutationFn: () => connectTeamsWebhook(url),
    onSuccess: () => { setUrl(""); qc.invalidateQueries({ queryKey: ["teams-webhook"] }); },
  });
  const disconnect = useMutation({
    mutationFn: disconnectTeamsWebhook,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["teams-webhook"] }),
  });
  const test = useMutation({
    mutationFn: () => testTeamsWebhook(id),
    onSuccess: () => setTestResult("ok"),
    onError: () => setTestResult("error"),
  });

  return (
    <div className="space-y-4">
      <div>
        <p className="font-medium">Microsoft Teams</p>
        <p className="text-sm text-muted-foreground">Get notified in a Teams channel when a tender is won or lost, and other worker events.</p>
      </div>

      {!status.data?.connected && (
        <Card className="border-amber-500/30 bg-amber-500/5"><CardContent className="space-y-2 pt-6 text-sm">
          <p className="font-medium">Set up an Incoming Webhook</p>
          <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>In Teams, open the channel you want notifications in.</li>
            <li>Channel menu {"\u2192"} Connectors (or Workflows) {"\u2192"} Incoming Webhook.</li>
            <li>Name it "Qiko", create it, and copy the webhook URL.</li>
          </ol>
        </CardContent></Card>
      )}

      <Card><CardContent className="space-y-4 pt-6">
        <p className="text-sm">Status: <span className="font-medium">{status.data?.connected ? "Connected" : "Not connected"}</span></p>
        {status.data?.connected ? (
          <div className="flex items-center gap-2">
            <Button variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? "Sending..." : "Send test notification"}
            </Button>
            <Button variant="outline" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
              Disconnect
            </Button>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="teams-webhook-url">Webhook URL</Label>
            <Input id="teams-webhook-url" placeholder="https://outlook.office.com/webhook/..." value={url} onChange={(e) => setUrl(e.target.value)} />
            <div className="flex justify-end pt-2">
              <Button disabled={!url || connect.isPending} onClick={() => connect.mutate()}>
                {connect.isPending ? "Connecting..." : "Connect"}
              </Button>
            </div>
          </div>
        )}
        {testResult === "ok" && <p className="text-xs text-emerald-600">Test notification sent -- check your Teams channel.</p>}
        {testResult === "error" && <p className="text-xs text-red-500">Could not reach Teams with that webhook URL.</p>}
      </CardContent></Card>
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
          <Label htmlFor="vapi-assistant-id">Assistant ID</Label>
          <Input id="vapi-assistant-id" placeholder="e.g. your-vapi-assistant-id" value={assistantId || creds.data?.vapi_assistant_id || ""}
            onChange={(e) => setAssistantId(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="vapi-public-key">Public Key</Label>
          <Input id="vapi-public-key" placeholder="pk-..." value={publicKey || creds.data?.vapi_public_key || ""}
            onChange={(e) => setPublicKey(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="vapi-secret-key">Secret Key</Label>
          <Input id="vapi-secret-key" type="password" placeholder={creds.data?.vapi_api_key_masked || "sk-..."} value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)} />
        </div>
        {save.isSuccess && <p className="text-xs text-emerald-600">Voice credentials saved.</p>}
        {save.isError && <p className="text-xs text-red-500">Couldn&apos;t save voice credentials. Check the values and try again.</p>}
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
  const qc = useQueryClient();
  const savedEventType = worker?.config?.calendly_event_type as string | undefined;
  const [url, setUrl] = useState("");
  const save = useMutation({
    mutationFn: () => updateCalendlyEventType(id, url),
    onSuccess: () => { setUrl(""); qc.invalidateQueries({ queryKey: ["agents"] }); },
  });

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
          <Label htmlFor="calendly-url">Calendly event type URL</Label>
          <Input id="calendly-url" placeholder="https://calendly.com/you/30min" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        {save.isSuccess && <p className="text-xs text-emerald-600">Calendly event saved.</p>}
        {save.isError && <p className="text-xs text-red-500">Couldn&apos;t save that Calendly event. Please try again.</p>}
        <div className="flex justify-end">
          <Button disabled={!url || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving..." : savedEventType ? "Change Calendly event" : "Connect Calendly"}
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
            className={cn("flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
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
      {step === "Behavior" && (
        <BehaviorStep key={worker ? "loaded" : "loading"} id={id} worker={worker} onSaved={onWorkerChange} />
      )}
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
        <Label htmlFor="bg-expertise">Your Expertise</Label>
        <Input id="bg-expertise" placeholder="e.g., RFP and Proposal Response Specialist for security services"
          value={expertise} onChange={(e) => setExpertise(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="bg-audience">Target Audience</Label>
        <Input id="bg-audience" placeholder="e.g., IDG bid, pre-sales, proposal, operations, and management team"
          value={audience} onChange={(e) => setAudience(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="bg-goal">Main Goal</Label>
        <Input id="bg-goal" placeholder="e.g., Help IDG review RFP documents, extract required sections and answer them"
          value={goal} onChange={(e) => setGoal(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="bg-unique">What makes you unique?</Label>
        <Textarea id="bg-unique" placeholder="e.g., Specialised in complex security tenders, compliance requirements..."
          value={unique} onChange={(e) => setUnique(e.target.value)} />
      </div>
      {save.isSuccess && <p className="text-xs text-emerald-600">Background saved.</p>}
      {save.isError && <p className="text-xs text-red-500">Couldn&apos;t save. Please try again.</p>}
      <div className="flex justify-end"><Button disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving..." : "Save Background"}</Button></div>
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
            className={cn("flex items-center gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
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

// Behavior sub-tab: Prompts / Guardrails / Rules. Each category is a string[] on the agent config,
// merge-patched via updateAgentConfig (config.prompts / config.guardrails / config.rules). This is
// persistence + UI only: it does not change how the backend generates answers.
const BEHAVIOR_CATEGORIES = [
  {
    key: "prompts", label: "Prompts", empty: "No prompts yet",
    help: "System prompts that shape how this worker introduces itself and responds.",
    placeholder: "e.g., Always greet the customer by name and confirm what they need before answering.",
  },
  {
    key: "guardrails", label: "Guardrails", empty: "No guardrails yet",
    help: "Limits on what this worker must never do or say.",
    placeholder: "e.g., Never share pricing before qualifying the lead.",
  },
  {
    key: "rules", label: "Rules", empty: "No rules yet",
    help: "Specific rules this worker should always follow.",
    placeholder: "e.g., Escalate to a human whenever a refund is requested.",
  },
] as const;
type BehaviorKey = (typeof BEHAVIOR_CATEGORIES)[number]["key"];

function BehaviorStep({ id, worker, onSaved }: { id: string; worker?: Agent; onSaved: () => void }) {
  const cfg = worker?.config ?? {};
  const seed = (k: BehaviorKey): string[] => {
    const v = cfg[k];
    return Array.isArray(v) ? (v as unknown[]).map((x) => String(x)) : [];
  };
  const [items, setItems] = useState<Record<BehaviorKey, string[]>>({
    prompts: seed("prompts"), guardrails: seed("guardrails"), rules: seed("rules"),
  });
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<BehaviorKey | null>("prompts");
  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => updateAgentConfig(id, patch),
    onSuccess: onSaved,
  });

  // Persist a category: store its cleaned (trimmed, non-empty) array under its config key.
  const persist = (key: BehaviorKey, next: string[]) => save.mutate({ [key]: next.map((s) => s.trim()).filter(Boolean) });
  const setCat = (key: BehaviorKey, next: string[]) => setItems((prev) => ({ ...prev, [key]: next }));
  const addItem = (key: BehaviorKey) => { setCat(key, [...items[key], ""]); setOpen(key); };
  const editItem = (key: BehaviorKey, i: number, value: string) => setCat(key, items[key].map((v, j) => (j === i ? value : v)));
  const removeItem = (key: BehaviorKey, i: number) => {
    const next = items[key].filter((_, j) => j !== i);
    setCat(key, next); persist(key, next);
  };

  const q = search.trim().toLowerCase();

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Behavior</h2>
        <p className="text-sm text-muted-foreground">Prompts &amp; rules</p>
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
        <Input placeholder="Search prompts, guardrails, and rules" value={search}
          onChange={(e) => setSearch(e.target.value)} aria-label="Search behavior" className="pl-9" />
      </div>

      {save.isError && <p className="text-xs text-red-500">Couldn&apos;t save that change. Please try again.</p>}

      <div className="space-y-3">
        {BEHAVIOR_CATEGORIES.map((c) => {
          const all = items[c.key];
          const visible = q ? all.map((v, i) => [v, i] as const).filter(([v]) => v.toLowerCase().includes(q)) : all.map((v, i) => [v, i] as const);
          const isOpen = open === c.key;
          return (
            <Card key={c.key} className="overflow-hidden">
              <div className="flex items-center justify-between gap-2 px-4 py-3">
                <button type="button" onClick={() => setOpen(isOpen ? null : c.key)}
                  className="flex flex-1 items-center gap-2 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60">
                  <ChevronDown className={cn("size-4 shrink-0 text-slate-500 transition-transform", !isOpen && "-rotate-90")} />
                  <span className="text-sm font-semibold text-white">{c.label}</span>
                  <span title={c.help} aria-label={c.help} className="cursor-help text-slate-500 hover:text-slate-300">
                    <HelpCircle className="size-3.5" />
                  </span>
                  <Badge variant="muted">{all.filter((s) => s.trim()).length}</Badge>
                </button>
                <Button variant="outline" size="sm" className="h-8 shrink-0" onClick={() => addItem(c.key)} disabled={save.isPending}>
                  <Plus className="size-4" /> Add
                </Button>
              </div>
              {isOpen && (
                <div className="space-y-2 border-t border-white/[0.06] px-4 py-3">
                  {all.length === 0 && (
                    <p className="py-2 text-sm text-muted-foreground">{c.empty}</p>
                  )}
                  {all.length > 0 && visible.length === 0 && (
                    <p className="py-2 text-sm text-muted-foreground">No matches.</p>
                  )}
                  {visible.map(([value, i]) => (
                    <div key={i} className="flex items-start gap-2">
                      <Textarea value={value} placeholder={c.placeholder}
                        onChange={(e) => editItem(c.key, i, e.target.value)}
                        onBlur={() => persist(c.key, items[c.key])}
                        className="min-h-16" />
                      <Button variant="ghost" size="icon" aria-label="Delete item" className="shrink-0"
                        disabled={save.isPending} onClick={() => removeItem(c.key, i)}>
                        <Trash2 className="size-4 text-muted-foreground" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

const KNOWLEDGE_CARDS = [
  { key: "faqs", title: "FAQs", description: "Common questions and answers your AI should know" },
  { key: "websites", title: "Websites", description: "URLs your AI can reference for information" },
  { key: "documents", title: "Documents", description: "PDFs, docs, or text files with important info" },
  { key: "policies", title: "Policies", description: "Rules, terms, or guidelines your AI must follow" },
] as const;

function KnowledgeStep({ id, docs, loading, onChange }: { id: string; docs?: Doc[]; loading: boolean; onChange: () => void }) {
  // Two views, matching stage-app: "Add New" (the category accordions + document ingestion) and
  // "Library" (the ingested documents, live from the shared per-worker KB that studio Sources reads).
  const [view, setView] = useState<"add" | "library">("add");
  const [open, setOpen] = useState<(typeof KNOWLEDGE_CARDS)[number]["key"] | null>("documents");
  const count = docs?.length ?? 0;

  function val(name: string): string {
    return (document.getElementById(`f-${name}`) as HTMLInputElement | HTMLTextAreaElement | null)?.value ?? "";
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Knowledge</h2>
        <p className="text-sm text-muted-foreground">FAQs &amp; docs</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant={view === "add" ? "default" : "outline"} size="sm" onClick={() => setView("add")}>
          <Plus className="size-4" /> Add New
        </Button>
        <Button variant={view === "library" ? "default" : "outline"} size="sm" onClick={() => setView("library")}>
          <Library className="size-4" /> Library ({count})
        </Button>
      </div>

      {view === "library" ? (
        <DocumentLibrary id={id} docs={docs} loading={loading} onChange={onChange} />
      ) : (
        <div className="space-y-3">
          {KNOWLEDGE_CARDS.map((c) => (
            <Card key={c.key}>
              <CardContent className="flex items-center justify-between py-4">
                <button className="flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60" onClick={() => setOpen(open === c.key ? null : c.key)}>
                  <p className="text-sm font-medium">{c.title}</p>
                  <p className="text-xs text-muted-foreground">{c.description}</p>
                </button>
                {c.key === "documents" && <Badge variant="muted">{count}</Badge>}
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
      )}
    </div>
  );
}

// The ingested-documents "Library": the SAME per-worker knowledge base the studio Sources tab reads
// (both use listDocuments / deleteDocument), so a doc added in either place shows up in the other.
function DocumentLibrary({ id, docs, loading, onChange }: { id: string; docs?: Doc[]; loading: boolean; onChange: () => void }) {
  const remove = useMutation({ mutationFn: (docId: string) => deleteDocument(docId, id), onSuccess: onChange });
  return (
    <div className="space-y-2">
      {loading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
      {!loading && (docs?.length ?? 0) === 0 && (
        <div className="flex flex-col items-center rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-12 text-center">
          <span className="mb-3 flex size-11 items-center justify-center rounded-2xl bg-white/[0.04] text-slate-500">
            <Database className="size-5" />
          </span>
          <p className="text-sm font-medium text-slate-300">Knowledge base is empty</p>
          <p className="mt-1 max-w-sm text-xs text-slate-500">Add a document from the Add New tab and it will appear here (and in studio Sources).</p>
        </div>
      )}
      {docs?.map((d) => (
        <Card key={d.doc_id}><CardContent className="flex items-center justify-between gap-3 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <FileText className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm font-medium text-white">{d.doc_id}</span>
            <Badge variant="muted">{d.chunks} passage{d.chunks === 1 ? "" : "s"}</Badge>
          </div>
          <Button variant="ghost" size="icon" aria-label={`Delete ${d.doc_id}`}
            disabled={remove.isPending && remove.variables === d.doc_id}
            onClick={() => { if (window.confirm(`Remove "${d.doc_id}" from the knowledge base?`)) remove.mutate(d.doc_id); }}>
            {remove.isPending && remove.variables === d.doc_id
              ? <Loader2 className="size-4 animate-spin text-muted-foreground" />
              : <Trash2 className="size-4 text-muted-foreground" />}
          </Button>
        </CardContent></Card>
      ))}
    </div>
  );
}

// Share a ready worker publicly (QIK-334 public link + QIK-336 website widget embed). The link opens
// the no-login guest chat at {origin}/chat/{id}; the embed snippet drops the floating chat widget
// (public/widget.js -> iframe /embed/{tenant}/{worker}) onto any external website.
function WorkerShare({ id, tenant }: { id: string; tenant: string }) {
  const [copied, setCopied] = useState<"" | "link" | "embed">("");
  const [showEmbed, setShowEmbed] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const embedSnippet =
    `<script src="${origin}/widget.js" data-tenant="${tenant}" data-worker="${id}" data-base="${origin}"></script>`;
  const copy = async (what: "link" | "embed", text: string) => {
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard blocked; ignore */ }
    setCopied(what);
    setTimeout(() => setCopied(""), 1500);
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" className="gap-1.5"
          onClick={() => copy("link", `${origin}/chat/${id}`)}>
          <Share2 className="size-3.5" /> {copied === "link" ? "Link copied" : "Copy public link"}
        </Button>
        <Button type="button" variant="outline" size="sm" className="gap-1.5"
          aria-expanded={showEmbed} onClick={() => setShowEmbed((v) => !v)}>
          <Share2 className="size-3.5" /> Embed on website
        </Button>
      </div>
      {showEmbed && (
        <div className="space-y-2 rounded-lg border border-border bg-white/[0.02] p-3">
          <p className="text-xs text-muted-foreground">Paste this before the closing &lt;/body&gt; tag on your site to add a floating chat widget.</p>
          <pre className="overflow-x-auto rounded bg-black/40 p-2 text-xs text-slate-200"><code>{embedSnippet}</code></pre>
          <Button type="button" variant="outline" size="sm" onClick={() => copy("embed", embedSnippet)}>
            {copied === "embed" ? "Embed code copied" : "Copy embed code"}
          </Button>
        </div>
      )}
    </div>
  );
}

function ChatTab({ id, worker }: { id: string; worker?: Agent }) {
  const [conversationId] = useState(() => `test-${Date.now()}`);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [busy, setBusy] = useState(false);
  // Config-driven, not hardcoded to any one worker: set via PUT /agents/{id}/config
  // (config.quick_prompts) so any specialised worker (pre-sales writer, tender assistant, ...)
  // can offer its own starting points instead of a blank "ask anything" box.
  const quickPrompts = (worker?.config?.quick_prompts as string[] | undefined) ?? [];

  async function sendText(q: string) {
    if (!q || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const reply = await ask(conversationId, q, id);
      setMessages((m) => [...m, reply]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Sorry, I couldn't answer that just now. Please try again in a moment." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">Test how this worker answers, grounded in the knowledge you&apos;ve added.</p>
          {worker?.status === "ready" && <WorkerShare id={id} tenant={worker.tenant} />}
        </div>
        {messages.length === 0 && quickPrompts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {quickPrompts.map((p) => (
              <button key={p} type="button" onClick={() => sendText(p)}
                className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60">
                {p}
              </button>
            ))}
          </div>
        )}
        <div className="min-h-40 space-y-2 rounded-lg border border-border p-3">
          {messages.length === 0 && (
            <div className="flex min-h-40 flex-col items-center justify-center py-8 text-center">
              <MessageSquare className="mb-2 size-8 text-slate-600" />
              <p className="text-sm font-medium text-slate-300">Test your worker</p>
              <p className="mt-0.5 max-w-xs text-xs text-slate-500">Ask a question to see a grounded reply from its knowledge base.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <ChatBubble role={m.role} text={m.text} />
            </div>
          ))}
          {busy && <div className="flex justify-start"><TypingIndicator /></div>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); sendText(input); }} className="flex gap-2">
          <Input placeholder="Ask your worker something…" value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} aria-label="Ask your worker something" />
          <Button type="submit" aria-label="Send message" disabled={busy || !input}><SendHorizonal className="size-4" /></Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SettingsTab({ id, worker, onWorkerChange }: { id: string; worker?: Agent; onWorkerChange: () => void }) {
  const cfg = worker?.config ?? {};
  // Full Name defaults to the agent's top-level name (which has no dedicated update endpoint),
  // then persists into config.full_name; the other three are free-form config keys. All four are
  // saved through the same updateAgentConfig merge-patch the Train/Background tab uses.
  const initial = {
    fullName: (cfg.full_name as string) ?? worker?.name ?? "",
    title: (cfg.title as string) ?? "",
    location: (cfg.location as string) ?? "",
    about: (cfg.about as string) ?? "",
  };
  const [fullName, setFullName] = useState(initial.fullName);
  const [title, setTitle] = useState(initial.title);
  const [location, setLocation] = useState(initial.location);
  const [about, setAbout] = useState(initial.about);
  const dirty =
    fullName !== initial.fullName || title !== initial.title ||
    location !== initial.location || about !== initial.about;

  const ready = worker?.status === "ready";
  const toggleStatus = useMutation({ mutationFn: () => markReady(id), onSuccess: onWorkerChange });
  const save = useMutation({
    mutationFn: () => updateAgentConfig(id, { full_name: fullName, title, location, about }),
    onSuccess: onWorkerChange,
  });
  // Studio membership is an explicit per-worker flag (config.studio_linked); Studio lists only
  // ready workers that have been pushed. Uses the same config merge-patch as everything else.
  const studioLinked = cfg.studio_linked === true;
  const pushStudio = useMutation({
    mutationFn: () => updateAgentConfig(id, { studio_linked: !studioLinked }),
    onSuccess: onWorkerChange,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Worker Settings</h1>
        <p className="text-muted-foreground">Manage your digital worker&apos;s profile and configuration</p>
      </div>

      <Card className="rounded-2xl"><CardContent className="space-y-4 pt-6">
        <div>
          <p className="text-sm font-semibold text-white">Worker Status</p>
          <p className="text-xs text-muted-foreground">Control whether this worker is still training or ready to serve.</p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
            ready ? "bg-emerald-500/15 text-emerald-400" : "bg-white/[0.06] text-slate-300")}>
            <span className={cn("size-1.5 rounded-full", ready ? "bg-emerald-400" : "bg-slate-400")} />
            {ready ? "Ready" : "Training"}
          </span>
          <Button
            variant={ready ? "outline" : "default"}
            disabled={ready || toggleStatus.isPending}
            title={ready ? "Reverting a ready worker to training isn't available yet" : undefined}
            onClick={() => { if (!ready) toggleStatus.mutate(); }}
          >
            {ready ? "Switch to Training" : toggleStatus.isPending ? "Switching…" : "Switch to Ready"}
          </Button>
        </div>
        {ready && (
          <p className="text-xs text-muted-foreground">Reverting a ready worker back to training isn&apos;t supported yet.</p>
        )}
        {toggleStatus.isError && <p className="text-xs text-red-500">Couldn&apos;t update the worker status. Please try again.</p>}
      </CardContent></Card>

      <Card className="rounded-2xl"><CardContent className="space-y-4 pt-6">
        <div>
          <p className="text-sm font-semibold text-white">Studio</p>
          <p className="text-xs text-muted-foreground">Push a ready worker to Studio to operate it day to day. Only ready workers can be pushed.</p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
            studioLinked ? "bg-cyan-500/15 text-cyan-300" : "bg-white/[0.06] text-slate-300")}>
            <span className={cn("size-1.5 rounded-full", studioLinked ? "bg-cyan-400" : "bg-slate-400")} />
            {studioLinked ? "In Studio" : "Not in Studio"}
          </span>
          <Button
            variant={studioLinked ? "outline" : "default"}
            disabled={(!ready && !studioLinked) || pushStudio.isPending}
            title={!ready && !studioLinked ? "Make the worker Ready before pushing it to Studio" : undefined}
            onClick={() => pushStudio.mutate()}
          >
            {pushStudio.isPending ? "Saving…" : studioLinked ? "Remove from Studio" : "Push to Studio"}
          </Button>
        </div>
        {pushStudio.isSuccess && !pushStudio.isPending && (
          <p className="text-xs text-emerald-400">{studioLinked ? "Worker pushed to Studio." : "Worker removed from Studio."}</p>
        )}
        {pushStudio.isError && <p className="text-xs text-red-500">Couldn&apos;t update Studio. Please try again.</p>}
      </CardContent></Card>

      <Card className="rounded-2xl"><CardContent className="space-y-4 pt-6">
        <div>
          <p className="text-sm font-semibold text-white">Profile Settings</p>
          <p className="text-xs text-muted-foreground">Details your worker uses to introduce itself.</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="set-fullname">Full Name</Label>
          <Input id="set-fullname" placeholder="e.g., Ava Thompson" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="set-title">Professional Title</Label>
          <Input id="set-title" placeholder="e.g., Pre-Sales Solutions Specialist" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="set-location">Location</Label>
          <Input id="set-location" placeholder="e.g., Dubai, UAE" value={location} onChange={(e) => setLocation(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="set-about">About Yourself</Label>
          <Textarea id="set-about" placeholder="A short summary of what this worker does and how it helps." value={about} onChange={(e) => setAbout(e.target.value)} />
        </div>
        {save.isSuccess && !dirty && <p className="text-xs text-emerald-600">Profile saved.</p>}
        {save.isError && <p className="text-xs text-red-500">Couldn&apos;t save. Please try again.</p>}
        <div className="flex items-center justify-end gap-3">
          {dirty && <p className="text-xs text-amber-400">You have unsaved changes</p>}
          <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save Changes"}
          </Button>
        </div>
      </CardContent></Card>
    </div>
  );
}

// Documents accordion: adds to the shared per-worker knowledge base. A "Choose file" picker + an
// "Ingest" button upload via ingestFile -> POST /knowledge/ingest-file (editor role), mirroring the
// studio Sources UX; free-text ingest stays as a lightweight alternative. Both refetch on success.
function KnowledgeTab({ id, docs, loading, onChange }: { id: string; docs?: Doc[]; loading: boolean; onChange: () => void }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const add = useMutation({ mutationFn: () => ingest(`${id}-${Date.now()}`, text, id), onSuccess: () => { setText(""); onChange(); } });
  const remove = useMutation({ mutationFn: (d: string) => deleteDocument(d, id), onSuccess: onChange });
  const ingestDoc = useMutation({
    // doc_id is the filename without extension, mirroring the studio Sources ingest flow.
    mutationFn: (f: File) => ingestFile(f.name.replace(/\.[^.]+$/, "") || f.name, f, id),
    onSuccess: () => { setFile(null); onChange(); },
  });
  return (
    <div className="space-y-4">
      <Card><CardContent className="space-y-3 pt-6">
        <p className="text-sm font-medium text-white">Add a document</p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-white/[0.06] focus-within:ring-2 focus-within:ring-cyan-500">
            <Upload className="size-4" /> Choose file
            <input type="file" accept=".pdf,.docx,.txt,.md" className="hidden" aria-label="Choose knowledge document"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
          </label>
          <span className="min-w-0 flex-1 truncate text-xs text-slate-500">{file?.name ?? "No file chosen"}</span>
          <Button disabled={!file || ingestDoc.isPending} onClick={() => file && ingestDoc.mutate(file)}>
            {ingestDoc.isPending ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
            {ingestDoc.isPending ? "Ingesting…" : "Ingest"}
          </Button>
        </div>
        {ingestDoc.isError && (
          <p className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-xs text-red-300">
            <AlertTriangle className="size-3.5 shrink-0" /> Couldn&apos;t ingest that file (needs editor role). Please try again.
          </p>
        )}
      </CardContent></Card>

      <Card><CardContent className="space-y-3 pt-6">
        <p className="text-sm font-medium text-white">Or add free-text knowledge</p>
        <Textarea id="f-knowledge" placeholder="Add free-text knowledge…" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="flex justify-end"><Button disabled={!text.trim() || add.isPending} onClick={() => add.mutate()}>Add knowledge</Button></div>
      </CardContent></Card>

      <div className="space-y-2">
        {loading && [0, 1].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        {docs?.map((d) => (
          <Card key={d.doc_id}><CardContent className="flex items-center justify-between py-3">
            <div className="flex min-w-0 items-center gap-3"><FileText className="size-4 shrink-0 text-muted-foreground" />
              <span className="truncate text-sm font-medium">{d.doc_id}</span><Badge variant="muted">{d.chunks} passage{d.chunks === 1 ? "" : "s"}</Badge></div>
            <Button variant="ghost" size="icon" aria-label={`Delete ${d.doc_id}`}
              disabled={remove.isPending && remove.variables === d.doc_id}
              onClick={() => { if (window.confirm(`Remove "${d.doc_id}" from the knowledge base?`)) remove.mutate(d.doc_id); }}>
              {remove.isPending && remove.variables === d.doc_id
                ? <Loader2 className="size-4 animate-spin text-muted-foreground" />
                : <Trash2 className="size-4 text-muted-foreground" />}
            </Button>
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
      {m.isSuccess && <p className="text-sm text-success">Added. Grounding updated.</p>}
      <div className="flex justify-end"><Button disabled={m.isPending} onClick={() => m.mutate()}>Save</Button></div>
    </CardContent></Card>
  );
}
