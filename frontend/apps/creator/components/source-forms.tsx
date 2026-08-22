"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { Button, Dialog, Input, Label, Select, cn } from "@qiko/ui";
import {
  type IntelligenceSourceConnection,
  type QikoTrackPreview,
  connectIntelligenceSource,
  disconnectIntelligenceSource,
  getGitHubAppInstallUrl,
  getIntelligenceQikoTrackPreview,
  getIntelligenceSourceConnection,
  listSlackWatchedChannels,
  setSlackWatchedChannels,
  testIntelligenceSource,
} from "@/lib/api";

type OnChange = () => void;

function parseList(value: string) {
  return value.split(",").map((s) => s.trim()).filter(Boolean);
}

type TestDialogState = {
  open: boolean;
  title: string;
  message: string;
  success: boolean;
};

function TestResultDialog({ state, onClose }: { state: TestDialogState; onClose: () => void }) {
  const titleId = "test-result-title";
  return (
    <Dialog open={state.open} onClose={onClose} labelledBy={titleId} className="w-[min(94vw,24rem)]">
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          {state.success ? (
            <CheckCircle2 className="size-5 text-emerald-400" aria-hidden="true" />
          ) : (
            <AlertTriangle className="size-5 text-amber-400" aria-hidden="true" />
          )}
          <h2 id={titleId} className="text-base font-semibold text-white">{state.title}</h2>
        </div>
        <p className="whitespace-pre-wrap text-sm text-white/70">{state.message}</p>
        <Button onClick={onClose} className="w-full">Close</Button>
      </div>
    </Dialog>
  );
}

export function GithubForm({
  agentId,
  connection,
  onChange,
}: {
  agentId: string;
  connection: IntelligenceSourceConnection | undefined;
  onChange: OnChange;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [testDialog, setTestDialog] = useState<TestDialogState>({ open: false, title: "", message: "", success: false });
  const [polling, setPolling] = useState(false);
  const c = connection?.key === "github" ? connection : undefined;

  const showTest = (title: string, text: string, success: boolean) =>
    setTestDialog({ open: true, title, message: text, success });

  const disconnect = useMutation({
    mutationFn: () => disconnectIntelligenceSource(agentId, "github"),
    onSuccess: () => { setMessage(""); onChange(); },
  });

  const test = useMutation({
    mutationFn: () => testIntelligenceSource(agentId, "github"),
    onSuccess: (res) => {
      if (res.ok) showTest("Connection test passed", `Connected as ${res.user}.`, true);
      else showTest("Connection test failed", res.error ?? "Could not reach GitHub.", false);
    },
    onError: (e: Error) => showTest("Connection test failed", e.message, false),
  });

  const install = useMutation({
    mutationFn: () => getGitHubAppInstallUrl(agentId),
    onSuccess: (res) => {
      const popup = window.open(res.url, "github_app_install", "width=900,height=800");
      if (popup) setPolling(true);
      else setMessage("Pop-up blocked. Allow pop-ups and try again.");
    },
    onError: (e: Error) => setMessage(e.message),
  });

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(() => {
      getIntelligenceSourceConnection(agentId, "github").then((res) => {
        if (res.key === "github" && res.connected) {
          setPolling(false);
          onChange();
        }
      }).catch(() => {});
    }, 2000);
    return () => clearInterval(interval);
  }, [polling, agentId, onChange]);

  if (!c?.connected) {
    return (
      <div className="space-y-3">
        <Button variant="outline" className="w-full" disabled={install.isPending} onClick={() => install.mutate()}>
          {install.isPending && <Loader2 className="size-4 animate-spin" />} Connect GitHub App
        </Button>
        {polling && <p className="text-xs text-muted-foreground">Waiting for GitHub App authorization...</p>}
        {message && <p className="text-xs text-destructive">{message}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending && <Loader2 className="size-4 animate-spin" />} Test
        </Button>
        <Button variant="destructive" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
          {disconnect.isPending && <Loader2 className="size-4 animate-spin" />} Disconnect
        </Button>
      </div>
      <TestResultDialog state={testDialog} onClose={() => setTestDialog((s) => ({ ...s, open: false }))} />
    </div>
  );
}

export function QikoTrackForm({
  agentId,
  connection,
  onChange,
}: {
  agentId: string;
  connection: IntelligenceSourceConnection | undefined;
  onChange: OnChange;
}) {
  const c = connection?.key === "qiko_track" ? connection : undefined;
  const [message, setMessage] = useState<string | null>(null);
  const [testDialog, setTestDialog] = useState<TestDialogState>({ open: false, title: "", message: "", success: false });

  const showTest = (title: string, text: string, success: boolean) =>
    setTestDialog({ open: true, title, message: text, success });

  const [token, setToken] = useState("");
  const [projectKeys, setProjectKeys] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [projectKey, setProjectKey] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectKind, setProjectKind] = useState<"INTERNAL" | "PRODUCT" | "CLIENT">("INTERNAL");
  const [existingKey, setExistingKey] = useState("");

  const preview = useQuery<QikoTrackPreview>({
    queryKey: ["qiko-track-preview", agentId],
    queryFn: () => getIntelligenceQikoTrackPreview(agentId),
    enabled: !c?.connected,
  });

  const connectManual = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "qiko_track", {
      token,
      project_keys: parseList(projectKeys),
      base_url: baseUrl || undefined,
    }),
    onSuccess: () => { setToken(""); setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const connectAuto = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "qiko_track", {
      auto: true,
      project_key: existingKey || projectKey,
      project_name: projectName,
      project_kind: projectKind,
      base_url: baseUrl || undefined,
    }),
    onSuccess: () => { setDialogOpen(false); setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const disconnect = useMutation({
    mutationFn: () => disconnectIntelligenceSource(agentId, "qiko_track"),
    onSuccess: () => { setMessage(null); onChange(); },
  });

  const test = useMutation({
    mutationFn: () => testIntelligenceSource(agentId, "qiko_track"),
    onSuccess: (res) => {
      if (res.ok) showTest("Connection test passed", "Qiko Track is reachable.", true);
      else showTest("Connection test failed", res.error ?? "Could not reach Qiko Track.", false);
    },
    onError: (e: Error) => showTest("Connection test failed", e.message, false),
  });

  useEffect(() => {
    if (preview.data?.suggested) {
      setProjectKey(preview.data.suggested.key);
      setProjectName(preview.data.suggested.name);
      setProjectKind(preview.data.suggested.kind);
    }
  }, [preview.data]);

  useEffect(() => {
    if (existingKey && preview.data?.existing_projects) {
      const selected = preview.data.existing_projects.find((p) => p.key === existingKey);
      if (selected) {
        setProjectKey(selected.key);
        setProjectName(selected.name);
        setProjectKind(selected.kind);
      }
    }
  }, [existingKey, preview.data]);

  if (c?.connected) {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
            {test.isPending && <Loader2 className="size-4 animate-spin" />} Test
          </Button>
          <Button variant="destructive" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
            {disconnect.isPending && <Loader2 className="size-4 animate-spin" />} Disconnect
          </Button>
        </div>
        <TestResultDialog state={testDialog} onClose={() => setTestDialog((s) => ({ ...s, open: false }))} />
      </div>
    );
  }

  if (preview.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading Qiko Track preview...</p>;
  }

  if (preview.isError || !preview.data) {
    return <p className="text-sm text-destructive">Could not load Qiko Track preview.</p>;
  }

  if (!preview.data.service_token_configured) {
    return (
      <div className="space-y-3">
        <div className="space-y-1">
          <Label className="text-xs">API token</Label>
          <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste Qiko Track token" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Base URL (optional, defaults to https://track.qiko.ai)</Label>
          <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://track.qiko.ai" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Project keys (comma separated)</Label>
          <Input value={projectKeys} onChange={(e) => setProjectKeys(e.target.value)} placeholder="QIW, PROJ-1" />
        </div>
        <Button disabled={!token || !projectKeys || connectManual.isPending} onClick={() => connectManual.mutate()} className="w-full">
          {connectManual.isPending && <Loader2 className="size-4 animate-spin" />} Connect
        </Button>
        {message && <p className="text-xs text-muted-foreground">{message}</p>}
      </div>
    );
  }

  const existing = preview.data.existing_projects;
  const selectedKey = existingKey || projectKey;

  return (
    <div className="space-y-3">
      <Button disabled={connectAuto.isPending} onClick={() => setDialogOpen(true)} className="w-full">
        {connectAuto.isPending && <Loader2 className="size-4 animate-spin" />} Connect Qiko Track
      </Button>
      {message && <p className="text-xs text-destructive">{message}</p>}

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        labelledBy="qiko-track-connect-title"
        busy={connectAuto.isPending}
      >
        <div className="space-y-4">
          <h2 id="qiko-track-connect-title" className="text-lg font-semibold">Connect Qiko Track</h2>
          <p className="text-sm text-muted-foreground">This worker will watch all Qiko Track projects. Choose or create the project where backlog proposals will be created.</p>

          {existing.length > 0 && (
            <div className="space-y-1">
              <Label className="text-xs">Backlog project</Label>
              <Select value={existingKey} onChange={(e) => setExistingKey(e.target.value)}>
                <option value="">Create new</option>
                {existing.map((p) => (
                  <option key={p.key} value={p.key}>{p.name} ({p.key})</option>
                ))}
              </Select>
            </div>
          )}

          <div className="space-y-1">
            <Label className="text-xs">Backlog project key</Label>
            <Input value={projectKey} onChange={(e) => setProjectKey(e.target.value.toUpperCase())} placeholder="QIW" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Backlog project name</Label>
            <Input value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="Qiko Intelligence Worker" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Kind</Label>
            <Select value={projectKind} onChange={(e) => setProjectKind(e.target.value as typeof projectKind)}>
              <option value="INTERNAL">Internal</option>
              <option value="PRODUCT">Product</option>
              <option value="CLIENT">Client</option>
            </Select>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={!selectedKey || connectAuto.isPending} onClick={() => connectAuto.mutate()}>
              {connectAuto.isPending && <Loader2 className="size-4 animate-spin" />} Connect
            </Button>
            <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

export function SlackForm({
  agentId,
  connection,
  onChange,
}: {
  agentId: string;
  connection: IntelligenceSourceConnection | undefined;
  onChange: OnChange;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const c = connection?.key === "slack" ? connection : undefined;

  const watched = useQuery({
    queryKey: ["slack-watched-channels", agentId],
    queryFn: () => listSlackWatchedChannels(agentId),
    enabled: !!c?.team_id,
  });

  useEffect(() => {
    const ids = new Set(watched.data?.watched_channels ?? c?.watched_channels ?? []);
    setSelected(ids);
  }, [watched.data, c]);

  const connect = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "slack"),
    onSuccess: (res) => {
      setMessage(null);
      if (res.url) {
        const popup = window.open(res.url, "slack_oauth", "width=500,height=700");
        if (popup) setPolling(true);
        else setMessage("Pop-up blocked. Please allow pop-ups and try again.");
      } else {
        onChange();
      }
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const saveChannels = useMutation({
    mutationFn: () => setSlackWatchedChannels(agentId, Array.from(selected)),
    onSuccess: () => { setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const disconnect = useMutation({
    mutationFn: () => disconnectIntelligenceSource(agentId, "slack"),
    onSuccess: () => { setMessage(null); onChange(); },
  });

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(() => {
      getIntelligenceSourceConnection(agentId, "slack").then((res) => {
        if (res.key === "slack" && res.team_id) {
          setPolling(false);
          onChange();
        }
      }).catch(() => {});
    }, 2000);
    return () => clearInterval(interval);
  }, [polling, agentId, onChange]);

  if (!c?.team_id) {
    return (
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">Authorize the Qiko Slack app for this worker.</p>
        <Button disabled={connect.isPending} onClick={() => connect.mutate()} className="w-full">
          {connect.isPending && <Loader2 className="size-4 animate-spin" />} Connect Slack
        </Button>
        {polling && <p className="text-xs text-muted-foreground">Waiting for Slack authorization...</p>}
        {message && <p className="text-xs text-destructive">{message}</p>}
      </div>
    );
  }

  const channels = watched.data?.channels ?? [];

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Team: {c.team_id}</p>
      <div className="max-h-40 space-y-2 overflow-y-auto rounded border border-white/[0.08] bg-white/[0.03] p-2">
        {channels.length === 0 && <p className="text-xs text-muted-foreground">No public channels found.</p>}
        {channels.map((ch) => (
          <label key={ch.id} className="flex items-center gap-2 text-xs text-white/80">
            <input
              type="checkbox"
              className="size-4 rounded border-white/[0.08] bg-white/[0.05]"
              checked={selected.has(ch.id)}
              onChange={(e) => {
                const next = new Set(selected);
                if (e.target.checked) next.add(ch.id);
                else next.delete(ch.id);
                setSelected(next);
              }}
            />
            #{ch.name}
          </label>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={saveChannels.isPending} onClick={() => saveChannels.mutate()}>
          {saveChannels.isPending && <Loader2 className="size-4 animate-spin" />} Save channels
        </Button>
        <Button variant="destructive" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
          {disconnect.isPending && <Loader2 className="size-4 animate-spin" />} Disconnect
        </Button>
      </div>
      {message && <p className="text-xs text-emerald-400">{message}</p>}
    </div>
  );
}
