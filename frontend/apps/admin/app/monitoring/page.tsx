"use client";

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, Button, Card, CardContent, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { formatUsd, workerMonitoring } from "@/lib/api";

const WINDOWS = [7, 30, 90] as const;
// Must match pagination.PAGE_SIZE on the server. The response does not report the page size, so the
// client cannot derive the page count without knowing it.
const PAGE_SIZE = 20;

export default function MonitoringPage() {
  const [days, setDays] = useState<number>(30);
  const [page, setPage] = useState(1);
  const monitoring = useQuery({
    queryKey: ["worker-monitoring", days, page],
    // The endpoint has always been paginated and this page never sent a page, so every worker past
    // the twentieth was unreachable while the heading truthfully reported the full total. An operator
    // scanning for a runaway worker would simply not have seen it.
    queryFn: () => workerMonitoring(days, page),
    placeholderData: keepPreviousData,
  });
  const pageCount = monitoring.data ? Math.max(1, Math.ceil(monitoring.data.total / PAGE_SIZE)) : 1;
  const shown = monitoring.data?.items.length ?? 0;
  const firstOnPage = shown === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;

  return (
    <AppShell title="Worker Monitoring">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Worker Monitoring</h1>
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {monitoring.isLoading ? "Loading workers..."
                : monitoring.data
                  ? `Showing ${firstOnPage}-${(page - 1) * PAGE_SIZE + shown} of ${monitoring.data.total} workers, busiest first`
                  : "Unavailable"}
            </p>
          </div>
          <div role="group" aria-label="Time window" className="flex gap-2">
            {WINDOWS.map((option) => (
              <Button key={option} className="min-h-11" aria-pressed={days === option}
                variant={days === option ? "default" : "outline"}
                onClick={() => { setDays(option); setPage(1); }}>
                {option}d
              </Button>
            ))}
          </div>
        </div>

        {monitoring.isError && (
          <Card><CardContent role="alert" className="py-6 text-sm text-destructive">
            Couldn&apos;t load worker activity.{" "}
            <button className="underline" onClick={() => monitoring.refetch()}>Retry</button>
          </CardContent></Card>
        )}

        <div className="space-y-3" aria-busy={monitoring.isFetching}>
          {monitoring.isLoading && [0, 1, 2].map((index) => <Skeleton key={index} className="h-20 w-full" />)}
          {monitoring.data?.items.length === 0 && (
            <Card><CardContent className="py-6 text-sm text-muted-foreground">No workers yet.</CardContent></Card>
          )}
          {monitoring.data?.items.map((worker) => (
            <Card key={`${worker.tenant_id}-${worker.id}`}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
                <div className="min-w-0">
                  <p className="truncate font-medium">{worker.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{worker.tenant_id} - {worker.id}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant="muted">{worker.status}</Badge>
                  <Badge variant={worker.enabled ? "default" : "destructive"}>
                    {worker.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                  <span className="text-muted-foreground">
                    {worker.calls} {worker.calls === 1 ? "call" : "calls"}
                  </span>
                  <span className="text-muted-foreground">
                    {/* Derived from real model activity rather than a heartbeat, so an idle worker
                        honestly reads as never used in this window. */}
                    {worker.last_seen
                      ? `last used ${new Date(worker.last_seen).toLocaleDateString()}`
                      : "not used in this window"}
                  </span>
                  {worker.cost_nano_usd !== undefined && (
                    <span className="tabular-nums">{formatUsd(worker.cost_nano_usd)}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {pageCount > 1 && (
          <nav aria-label="Worker pagination" className="flex items-center justify-between gap-3">
            <Button variant="outline" className="min-h-11" disabled={page <= 1 || monitoring.isFetching}
              onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</Button>
            <span className="text-sm text-muted-foreground">Page {page} of {pageCount}</span>
            <Button variant="outline" className="min-h-11"
              disabled={page >= pageCount || monitoring.isFetching}
              onClick={() => setPage((current) => current + 1)}>Next</Button>
          </nav>
        )}

        {monitoring.data && !monitoring.data.cost_visible && (
          <p role="status" className="text-sm text-muted-foreground">
            Spend is hidden: showing it needs the View AI cost capability.
          </p>
        )}
      </div>
    </AppShell>
  );
}
