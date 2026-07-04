"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Users } from "lucide-react";
import { Card, CardContent, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { analytics } from "@/lib/api";

export default function AnalyticsPage() {
  const a = useQuery({ queryKey: ["analytics"], queryFn: analytics });

  return (
    <AppShell title="Analytics">
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Analytics</h2>
          <p className="text-sm text-muted-foreground">Traffic from Google Analytics (GA4).</p>
        </div>

        {a.isError && <Card><CardContent className="py-6 text-sm text-destructive">Not authorized (admin role required).</CardContent></Card>}

        {a.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
        ) : a.data && (
          <>
            {!a.data.had_data && (
              <Card><CardContent className="py-4 text-sm text-muted-foreground">
                No GA4 data yet — configure GA4 credentials to see live traffic.
              </CardContent></Card>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Card><CardContent className="flex items-center gap-4 py-5">
                <span className="grid size-11 place-items-center rounded-lg bg-accent text-accent-foreground"><Activity className="size-5" /></span>
                <div><p className="text-2xl font-semibold tabular-nums">{a.data.sessions}</p><p className="text-sm text-muted-foreground">Sessions</p></div>
              </CardContent></Card>
              <Card><CardContent className="flex items-center gap-4 py-5">
                <span className="grid size-11 place-items-center rounded-lg bg-accent text-accent-foreground"><Users className="size-5" /></span>
                <div><p className="text-2xl font-semibold tabular-nums">{a.data.active_users}</p><p className="text-sm text-muted-foreground">Active users</p></div>
              </CardContent></Card>
            </div>
            <Card>
              <CardContent className="space-y-2 pt-6">
                <h3 className="text-sm font-medium text-muted-foreground">Top pages</h3>
                {a.data.top_pages.length === 0 && <p className="text-sm text-muted-foreground">No data.</p>}
                {a.data.top_pages.map((p) => (
                  <div key={p.pagePath} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                    <span className="text-sm">{p.pagePath}</span>
                    <span className="text-sm font-semibold tabular-nums">{p.sessions}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </AppShell>
  );
}
