"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Button, Input, Label, cn } from "@qiko/ui";
import {
  type IntelligenceSourceConnection,
  connectIntelligenceSource,
  disconnectIntelligenceSource,
  getGitHubAppInstallUrl,
  getIntelligenceSourceConnection,
  listSlackWatchedChannels,
  setSlackWatchedChannels,
  testIntelligenceSource,
} from "@/lib/api";

type OnChange = () => void;

function parseList(value: string) {
  return value.split(",").map((s) => s.trim()).filter(Boolean);
}

function formatList(items: string[]) {
  return items.join(", ");
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
  const [token, setToken] = useState("");
  const [repos, setRepos] = useState("");
  const [branches, setBranches] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const c = connection?.key === "github" ? connection : undefined;

  const connect = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "github", {
      token,
      repo_allowlist: parseList(repos),
      watched_branches: parseList(branches),
    }),
    onSuccess: () => { setToken(""); setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const save = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "github", {
      repo_allowlist: parseList(repos),
      watched_branches: parseList(branches),
    }),
    onSuccess: () => { setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const disconnect = useMutation({
    mutationFn: () => disconnectIntelligenceSource(agentId, "github"),
    onSuccess: () => { setMessage(null); onChange(); },
  });

  const test = useMutation({
    mutationFn: () => testIntelligenceSource(agentId, "github"),
    onSuccess: (res) => setMessage(res.ok ? `Connected as ${res.user}` : (res.error ?? "Test failed")),
    onError: (e: Error) => setMessage(e.message),
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

  useEffect(() => {
    if (c) {
      setRepos(formatList(c.repo_allowlist ?? []));
      setBranches(formatList(c.watched_branches ?? []));
    }
  }, [c]);

  if (!c?.connected) {
    return (
      <div className="space-y-3">
        <Button variant="outline" className="w-full" disabled={install.isPending} onClick={() => install.mutate()}>
          {install.isPending && <Loader2 className="size-4 animate-spin" />} Connect GitHub App
        </Button>
        <p className="text-xs text-muted-foreground text-center">or use a personal access token</p>
        <div className="space-y-1">
          <Label className="text-xs">Personal access token</Label>
          <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="ghp_..." />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Repo allowlist (owner/repo, comma separated)</Label>
          <Input value={repos} onChange={(e) => setRepos(e.target.value)} placeholder="acme/api, acme/web" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Watched branches (comma separated, optional)</Label>
          <Input value={branches} onChange={(e) => setBranches(e.target.value)} placeholder="main, develop" />
        </div>
        <Button disabled={!token || connect.isPending} onClick={() => connect.mutate()} className="w-full">
          {connect.isPending && <Loader2 className="size-4 animate-spin" />} Connect
        </Button>
        {polling && <p className="text-xs text-muted-foreground">Waiting for GitHub App authorization...</p>}
        {message && <p className="text-xs text-destructive">{message}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Token: {c.token_masked || "saved"}</p>
      <div className="space-y-1">
        <Label className="text-xs">Repo allowlist</Label>
        <Input value={repos} onChange={(e) => setRepos(e.target.value)} placeholder="acme/api, acme/web" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Watched branches</Label>
        <Input value={branches} onChange={(e) => setBranches(e.target.value)} placeholder="main, develop" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending && <Loader2 className="size-4 animate-spin" />} Save
        </Button>
        <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending && <Loader2 className="size-4 animate-spin" />} Test
        </Button>
        <Button variant="outline" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
          Disconnect
        </Button>
      </div>
      {message && (
        <p className={cn("text-xs", message.includes("failed") || message.includes("error") ? "text-destructive" : "text-emerald-400")}>
          {message}
        </p>
      )}
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
  const [token, setToken] = useState("");
  const [projectKeys, setProjectKeys] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const c = connection?.key === "qiko_track" ? connection : undefined;

  const connect = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "qiko_track", {
      token,
      project_keys: parseList(projectKeys),
      base_url: baseUrl || undefined,
    }),
    onSuccess: () => { setToken(""); setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const save = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "qiko_track", {
      project_keys: parseList(projectKeys),
      base_url: baseUrl || undefined,
    }),
    onSuccess: () => { setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const disconnect = useMutation({
    mutationFn: () => disconnectIntelligenceSource(agentId, "qiko_track"),
    onSuccess: () => { setMessage(null); onChange(); },
  });

  const test = useMutation({
    mutationFn: () => testIntelligenceSource(agentId, "qiko_track"),
    onSuccess: (res) => setMessage(res.ok ? "Test passed" : (res.error ?? "Test failed")),
    onError: (e: Error) => setMessage(e.message),
  });

  useEffect(() => {
    if (c) {
      setProjectKeys(formatList(c.project_keys ?? []));
      setBaseUrl(c.base_url ?? "");
    }
  }, [c]);

  if (!c?.connected) {
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
        <Button disabled={!token || !projectKeys || connect.isPending} onClick={() => connect.mutate()} className="w-full">
          {connect.isPending && <Loader2 className="size-4 animate-spin" />} Connect
        </Button>
        {message && <p className="text-xs text-muted-foreground">{message}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Token: {c.token_masked || "saved"}</p>
      <div className="space-y-1">
        <Label className="text-xs">Base URL</Label>
        <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://track.qiko.ai" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Project keys</Label>
        <Input value={projectKeys} onChange={(e) => setProjectKeys(e.target.value)} placeholder="QIW, PROJ-1" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending && <Loader2 className="size-4 animate-spin" />} Save
        </Button>
        <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending && <Loader2 className="size-4 animate-spin" />} Test
        </Button>
        <Button variant="outline" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
          Disconnect
        </Button>
      </div>
      {message && <p className={cn("text-xs", message.includes("failed") || message.includes("error") ? "text-destructive" : "text-emerald-400")}>{message}</p>}
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
        <Button variant="outline" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
          Disconnect
        </Button>
      </div>
      {message && <p className="text-xs text-emerald-400">{message}</p>}
    </div>
  );
}
