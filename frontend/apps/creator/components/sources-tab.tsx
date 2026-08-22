"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Badge, Card, CardContent, Logo } from "@qiko/ui";
import { type IntelligenceSource, getIntelligenceSourceConnection, listIntelligenceSources } from "@/lib/api";
import { GithubForm, QikoTrackForm, SlackForm } from "./source-forms";

function GitHubLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 98 96" xmlns="http://www.w3.org/2000/svg" className={className} aria-hidden="true">
      <path
        fillRule="evenodd" clipRule="evenodd"
        d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.22-22.229-5.378-22.229-24.13 0-5.34 1.824-9.69 5.044-13.1-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.001a39.39 39.39 0 0 1 20.48 0c9.299-6.358 13.426-5.001 13.426-5.001 2.67 6.763.97 11.816.485 13.038 3.155 3.41 5.044 7.76 5.044 13.1 0 18.847-11.404 22.841-22.321 24.118 1.78 1.548 3.316 4.481 3.316 9.11 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z"
        fill="currentColor"
      />
    </svg>
  );
}

function SlackLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 54 54" xmlns="http://www.w3.org/2000/svg" className={className} aria-hidden="true">
      <g fill="none" fillRule="evenodd">
        <path d="M19.712.133a5.381 5.381 0 0 0-5.376 5.388 5.381 5.381 0 0 0 5.376 5.386h5.376V5.521A5.381 5.381 0 0 0 19.712.133m0 14.365H5.376A5.381 5.381 0 0 0 0 19.884a5.381 5.381 0 0 0 5.376 5.387h14.336a5.381 5.381 0 0 0 5.376-5.387 5.381 5.381 0 0 0-5.376-5.386" fill="#E01E5A" />
        <path d="M53.76 19.884a5.381 5.381 0 0 0-5.376-5.386 5.381 5.381 0 0 0-5.376 5.386v5.387h5.376a5.381 5.381 0 0 0 5.376-5.387m-14.336 0V5.521a5.381 5.381 0 0 0-5.376-5.388 5.381 5.381 0 0 0-5.376 5.388v14.363a5.381 5.381 0 0 0 5.376 5.387 5.381 5.381 0 0 0 5.376-5.387" fill="#36C5F0" />
        <path d="M34.048 54a5.381 5.381 0 0 0 5.376-5.388 5.381 5.381 0 0 0-5.376-5.386H28.67v5.386A5.381 5.381 0 0 0 34.048 54m0-14.365h14.336a5.381 5.381 0 0 0 5.376-5.386 5.381 5.381 0 0 0-5.376-5.387H34.048a5.381 5.381 0 0 0-5.376 5.387 5.381 5.381 0 0 0 5.376 5.386" fill="#2EB67D" />
        <path d="M0 34.249a5.381 5.381 0 0 0 5.376 5.385 5.381 5.381 0 0 0 5.376-5.385V28.86H5.376A5.381 5.381 0 0 0 0 34.249m14.336-.001V48.612a5.381 5.381 0 0 0 5.376 5.388 5.381 5.381 0 0 0 5.376-5.388V34.248a5.381 5.381 0 0 0-5.376-5.386 5.381 5.381 0 0 0-5.376 5.386" fill="#ECB22E" />
      </g>
    </svg>
  );
}

function SourceIcon({ source }: { source: string }) {
  if (source === "github") return <GitHubLogo className="size-5" />;
  if (source === "slack") return <SlackLogo className="size-5" />;
  if (source === "qiko_track") return <Logo iconOnly className="size-5" />;
  return null;
}

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
        {sources.data
          ?.filter((source) => source.key !== "generic")
          .map((source) => (
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

  return (
    <Card className="bg-card">
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted">
              <SourceIcon source={source.key} />
            </span>
            <div>
              <h3 className="font-semibold text-foreground">{source.name}</h3>
              {!source.connected && <p className="text-xs text-muted-foreground">{source.description}</p>}
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