"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Button, Input, Label, cn } from "@qiko/ui";
import {
  type IntelligenceSourceConnection,
  connectIntelligenceSource,
  disconnectIntelligenceSource,
  getIntelligenceSourceConnection,
  listSlackWatchedChannels,
  setSlackWatchedChannels,
  testIntelligenceSource,
} from "@/lib/api";

type OnChange = () => void;

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
  const [message, setMessage] = useState<string | null>(null);
  const c = connection?.key === "github" ? connection : undefined;

  const connect = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "github", {
      token,
      repo_allowlist: repos.split(",").map((r) => r.trim()).filter(Boolean),
    }),
    onSuccess: () => { setToken(""); setMessage(null); onChange(); },
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

  if (!c?.connected) {
    return (
      <div className="space-y-3">
        <div className="space-y-1">
          <Label className="text-xs">Personal access token</Label>
          <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="ghp_..." />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Repo allowlist (owner/repo, comma separated)</Label>
          <Input value={repos} onChange={(e) => setRepos(e.target.value)} placeholder="acme/api, acme/web" />
        </div>
        <Button disabled={!token || connect.isPending} onClick={() => connect.mutate()} className="w-full">
          {connect.isPending && <Loader2 className="size-4 animate-spin" />} Connect
        </Button>
        {message && <p className="text-xs text-destructive">{message}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Token: {c.token_masked || "saved"}</p>
      {c.repo_allowlist.length > 0 && (
        <p className="text-xs text-muted-foreground">Repos: {c.repo_allowlist.join(", ")}</p>
      )}
      <div className="flex gap-2">
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
  const [projectKey, setProjectKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const c = connection?.key === "qiko_track" ? connection : undefined;

  const connect = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "qiko_track", { token, project_key: projectKey }),
    onSuccess: () => { setToken(""); setMessage(null); onChange(); },
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

  if (!c?.connected) {
    return (
      <div className="space-y-3">
        <div className="space-y-1">
          <Label className="text-xs">API token</Label>
          <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste Qiko Track token" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Project key</Label>
          <Input value={projectKey} onChange={(e) => setProjectKey(e.target.value)} placeholder="PROJ-1" />
        </div>
        <Button disabled={!token || !projectKey || connect.isPending} onClick={() => connect.mutate()} className="w-full">
          {connect.isPending && <Loader2 className="size-4 animate-spin" />} Connect
        </Button>
        {message && <p className="text-xs text-muted-foreground">{message}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Token: {c.token_masked || "saved"}</p>
      <p className="text-xs text-muted-foreground">Project: {c.project_key}</p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending && <Loader2 className="size-4 animate-spin" />} Test
        </Button>
        <Button variant="outline" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
          Disconnect
        </Button>
      </div>
      {message && <p className="text-xs text-destructive">{message}</p>}
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
  const [channels, setChannels] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const c = connection?.key === "slack" ? connection : undefined;

  const watched = useQuery({
    queryKey: ["slack-watched-channels", agentId],
    queryFn: () => listSlackWatchedChannels(agentId),
    enabled: !!c?.team_id,
  });

  const connect = useMutation({
    mutationFn: () => connectIntelligenceSource(agentId, "slack"),
    onSuccess: (res) => {
      setMessage(null);
      if (res.url) {
        const popup = window.open(res.url, "slack_oauth", "width=500,height=700");
        if (popup) {
          setPolling(true);
        } else {
          setMessage("Pop-up blocked. Please allow pop-ups and try again.");
        }
      } else {
        onChange();
      }
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const saveChannels = useMutation({
    mutationFn: () => setSlackWatchedChannels(agentId, channels.split(",").map((s) => s.trim()).filter(Boolean)),
    onSuccess: () => { setMessage(null); onChange(); },
    onError: (e: Error) => setMessage(e.message),
  });

  const disconnect = useMutation({
    mutationFn: () => disconnectIntelligenceSource(agentId, "slack"),
    onSuccess: () => { setChannels(""); setMessage(null); onChange(); },
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

  const current = watched.data?.watched_channels ?? c.watched_channels ?? [];

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Team: {c.team_id}</p>
      <div className="space-y-1">
        <Label className="text-xs">Watched channel IDs (comma separated)</Label>
        <Input
          defaultValue={current.join(", ")}
          onChange={(e) => setChannels(e.target.value)}
          placeholder="C123, C456"
        />
      </div>
      <div className="flex gap-2">
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
