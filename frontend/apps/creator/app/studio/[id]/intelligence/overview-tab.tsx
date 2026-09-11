"use client";

import { useQuery } from "@tanstack/react-query";
import { GitPullRequest, ListTodo, RefreshCw, Users } from "lucide-react";
import { Badge, cn } from "@qiko/ui";
import { getIntelligenceOverview, type OverviewDeveloper, type OverviewPr, type OverviewTicket } from "@/lib/api";

export function OverviewTab({ agentId }: { agentId: string }) {
  const overview = useQuery({
    queryKey: ["intelligence-overview", agentId],
    queryFn: () => getIntelligenceOverview(agentId),
  });

  if (overview.isLoading) return <PageSkeleton />;

  const data = overview.data;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button onClick={() => overview.refetch()} className="text-white/50 hover:text-white" aria-label="Refresh overview">
          <RefreshCw className={cn("size-4", overview.isFetching && "animate-spin")} />
        </button>
      </div>

      <section className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <GitPullRequest className="size-4 text-primary" /> Open PRs <Badge variant="muted">{data.open_prs.length}</Badge>
        </h2>
        {data.open_prs.length === 0 && <p className="text-sm text-white/50">No open PRs.</p>}
        {data.open_prs.length > 0 && (
          <ul className="space-y-2">
            {data.open_prs.map((pr) => (
              <OpenPrRow key={pr.ref} pr={pr} />
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <ListTodo className="size-4 text-primary" /> In progress <Badge variant="muted">{data.in_progress_tickets.length}</Badge>
        </h2>
        {data.in_progress_tickets.length === 0 && <p className="text-sm text-white/50">Nothing in progress.</p>}
        {data.in_progress_tickets.length > 0 && (
          <ul className="space-y-2">
            {data.in_progress_tickets.map((t) => (
              <InProgressRow key={t.ref} ticket={t} />
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <Users className="size-4 text-primary" /> Active developers
        </h2>
        {data.developers.length === 0 && <p className="text-sm text-white/50">No activity yet.</p>}
        {data.developers.length > 0 && (
          <ul className="space-y-2">
            {data.developers.map((d) => (
              <DeveloperRow key={d.actor} developer={d} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function OpenPrRow({ pr }: { pr: OverviewPr }) {
  return (
    <li className="flex items-center justify-between gap-3 text-sm">
      <div className="min-w-0">
        {pr.url ? (
          <a href={pr.url} target="_blank" rel="noreferrer" className="truncate text-white hover:underline">
            {pr.title}
          </a>
        ) : (
          <span className="truncate text-white">{pr.title}</span>
        )}
        <p className="text-xs text-white/40">
          {pr.container} - {pr.author} - {Math.round(pr.age_hours)}h old
        </p>
      </div>
      {pr.review_status && (
        <span className="shrink-0 rounded bg-white/[0.08] px-2 py-0.5 text-xs text-white/70">{pr.review_status}</span>
      )}
    </li>
  );
}

function InProgressRow({ ticket }: { ticket: OverviewTicket }) {
  return (
    <li className="flex items-center justify-between gap-3 text-sm">
      {ticket.url ? (
        <a href={ticket.url} target="_blank" rel="noreferrer" className="text-white hover:underline">
          {ticket.ref}
        </a>
      ) : (
        <span className="text-white">{ticket.ref}</span>
      )}
      <span className="shrink-0 text-xs text-white/40">{ticket.status} - {ticket.actor}</span>
    </li>
  );
}

function DeveloperRow({ developer }: { developer: OverviewDeveloper }) {
  return (
    <li className="flex items-center justify-between gap-3 text-sm">
      <span className="text-white">{developer.actor}</span>
      <span className="shrink-0 text-xs text-white/40">
        {developer.open_prs} open PRs - {developer.in_progress_tickets} in progress
      </span>
    </li>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl bg-white/[0.05]" />
      ))}
    </div>
  );
}
