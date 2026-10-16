"use client";

import { useQuery } from "@tanstack/react-query";
import { Inbox, MessageCircle, RefreshCw } from "lucide-react";
import { Badge, cn } from "@qiko/ui";
import { getIntelligenceEngagement, type EngagementActive, type EngagementAwaiting } from "@/lib/api";

export function EngagementTab({ agentId }: { agentId: string }) {
  const engagement = useQuery({
    queryKey: ["intelligence-engagement", agentId],
    queryFn: () => getIntelligenceEngagement(agentId),
  });

  if (engagement.isLoading) return <PageSkeleton />;

  const data = engagement.data;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button onClick={() => engagement.refetch()} className="text-slate-500 hover:text-foreground" aria-label="Refresh engagement">
          <RefreshCw className={cn("size-4", engagement.isFetching && "animate-spin")} />
        </button>
      </div>

      <section className="rounded-xl border border-border bg-muted p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
          <MessageCircle className="size-4 text-primary" /> Active in Slack <Badge variant="muted">{data.active.length}</Badge>
        </h2>
        {data.active.length === 0 && <p className="text-sm text-slate-500">No Slack activity yet.</p>}
        {data.active.length > 0 && (
          <ul className="space-y-2">
            {data.active.map((row) => (
              <ActiveRow key={row.actor} row={row} />
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-border bg-muted p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Inbox className="size-4 text-primary" /> Awaiting a reply <Badge variant="muted">{data.awaiting_response.length}</Badge>
        </h2>
        {data.awaiting_response.length === 0 && <p className="text-sm text-slate-500">Nothing waiting - inbox zero.</p>}
        {data.awaiting_response.length > 0 && (
          <ul className="space-y-2">
            {data.awaiting_response.map((row, i) => (
              <AwaitingRow key={`${row.container}-${row.mentioned}-${i}`} row={row} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ActiveRow({ row }: { row: EngagementActive }) {
  return (
    <li className="flex items-center justify-between gap-3 text-sm">
      <span className="text-foreground">{row.actor}</span>
      <span className="shrink-0 text-xs text-slate-400">
        {row.message_count} messages - {row.channels.join(", ")}
      </span>
    </li>
  );
}

function AwaitingRow({ row }: { row: EngagementAwaiting }) {
  const text = `${row.mentioned} has an unanswered mention from ${row.mentioned_by}, ${row.hours_waiting}h ago`;
  return (
    <li className="flex items-center justify-between gap-3 text-sm">
      {row.url ? (
        <a href={row.url} target="_blank" rel="noreferrer" className="truncate text-foreground hover:underline">
          {text}
        </a>
      ) : (
        <span className="truncate text-foreground">{text}</span>
      )}
      <span className="shrink-0 text-xs text-slate-400">{row.container}</span>
    </li>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 2 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-50" />
      ))}
    </div>
  );
}
