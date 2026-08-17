"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Github, Loader2, MessageCircle } from "lucide-react";
import { Badge, Card, CardContent } from "@qiko/ui";
import { type IntelligenceSource, getIntelligenceSourceConnection, listIntelligenceSources } from "@/lib/api";
import { GithubForm, QikoTrackForm, SlackForm } from "./source-forms";

const ICONS: Record<string, React.ElementType> = {
  slack: MessageCircle,
  github: Github,
  qiko_track: Database,
};

export function SourcesTab({ agentId }: { agentId: string }) {
  const qc = useQueryClient();
  const sources = useQuery({
    queryKey: ["intelligence-sources", agentId],
    queryFn: () => listIntelligenceSources(agentId),
  });

  if (sources.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Loading sources...
      </div>
    );
  }
  if (sources.isError) {
    return <p className="text-sm text-destructive">Could not load sources.</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Knowledge sources</h2>
        <p className="text-sm text-muted-foreground">
          Connect workspaces and tools this worker should learn from.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sources.data?.map((source) => (
          <SourceCard key={source.key} agentId={agentId} source={source} />
        ))}
      </div>
    </div>
  );
}

function SourceCard({ agentId, source }: { agentId: string; source: IntelligenceSource }) {
  const qc = useQueryClient();
  const connection = useQuery({
    queryKey: ["intelligence-source-connection", agentId, source.key],
    queryFn: () => getIntelligenceSourceConnection(agentId, source.key),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["intelligence-source-connection", agentId, source.key] });
    qc.invalidateQueries({ queryKey: ["intelligence-sources", agentId] });
  };

  const Icon = ICONS[source.key] ?? Database;

  return (
    <Card className="bg-card">
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted">
              <Icon className="size-5 text-foreground" />
            </span>
            <div>
              <h3 className="font-semibold text-foreground">{source.name}</h3>
              <p className="text-xs text-muted-foreground">{source.description}</p>
            </div>
          </div>
          <Badge variant={source.connected ? "success" : "muted"} className="shrink-0">
            {source.connected ? "Connected" : "Not connected"}
          </Badge>
        </div>

        {source.key === "github" && (
          <GithubForm agentId={agentId} connection={connection.data} onChange={invalidate} />
        )}
        {source.key === "qiko_track" && (
          <QikoTrackForm agentId={agentId} connection={connection.data} onChange={invalidate} />
        )}
        {source.key === "slack" && (
          <SlackForm agentId={agentId} connection={connection.data} onChange={invalidate} />
        )}
      </CardContent>
    </Card>
  );
}