"use client";

import { useQuery } from "@tanstack/react-query";
import { Badge, Card, CardContent, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { formatBytes, systemStats } from "@/lib/api";

function Row({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={warn ? "font-medium text-destructive tabular-nums" : "tabular-nums"}>{value}</span>
    </div>
  );
}

export default function SystemPage() {
  const stats = useQuery({ queryKey: ["system-stats"], queryFn: systemStats, refetchInterval: 30_000 });
  const data = stats.data;
  const database = data?.database;
  const redis = data?.redis;

  // Connection headroom is the number that actually predicts an outage, so it is computed rather than
  // left for the reader to divide two figures in their head.
  const connectionUse = database?.available && database.connections_limit
    ? Math.round(((database.connections_total ?? 0) / database.connections_limit) * 100)
    : null;

  return (
    <AppShell title="System">
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>System</h1>
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
            {stats.isLoading ? "Loading system state..."
              : data ? `${data.environment} - ${data.ready ? "ready" : "NOT ready"} - v${data.version}`
              : "Unavailable"}
          </p>
        </div>

        {stats.isError && (
          <Card><CardContent role="alert" className="py-6 text-sm text-destructive">
            Couldn&apos;t load system state.{" "}
            <button className="underline" onClick={() => stats.refetch()}>Retry</button>
          </CardContent></Card>
        )}
        {stats.isLoading && [0, 1, 2].map((index) => <Skeleton key={index} className="h-28 w-full" />)}

        {data && (
          <>
            <Card><CardContent className="space-y-2 py-4">
              <p className="font-medium">Dependencies</p>
              {data.checks.map((check) => (
                <div key={check.name} className="flex items-center justify-between gap-3 text-sm">
                  <span className="capitalize">{check.name}</span>
                  <span className="flex items-center gap-2">
                    {check.detail && <span className="text-xs text-muted-foreground">{check.detail}</span>}
                    {check.latency_ms !== null && (
                      <span className="text-xs text-muted-foreground tabular-nums">{check.latency_ms} ms</span>
                    )}
                    <Badge variant={check.ok ? "default" : "destructive"}>{check.ok ? "OK" : "Down"}</Badge>
                  </span>
                </div>
              ))}
            </CardContent></Card>

            <Card><CardContent className="space-y-2 py-4">
              <p className="font-medium">Database</p>
              {!database?.available && (
                <p className="text-sm text-muted-foreground">Not collected: {database?.reason}</p>
              )}
              {database?.available && (
                <>
                  <Row label="Size" value={formatBytes(database.size_bytes ?? 0)} />
                  <Row label="Connections" warn={(connectionUse ?? 0) >= 80}
                    value={`${database.connections_total} of ${database.connections_limit}${connectionUse !== null ? ` (${connectionUse}%)` : ""}`} />
                  <Row label="Active queries" value={String(database.connections_active ?? 0)} />
                </>
              )}
            </CardContent></Card>

            <Card><CardContent className="space-y-2 py-4">
              <p className="font-medium">Redis and queue</p>
              {!redis?.available && <p className="text-sm text-muted-foreground">Not collected: {redis?.reason}</p>}
              {redis?.available && (
                <>
                  <Row label="Memory" value={redis.max_memory_bytes
                    ? `${formatBytes(redis.used_memory_bytes ?? 0)} of ${formatBytes(redis.max_memory_bytes)}`
                    : formatBytes(redis.used_memory_bytes ?? 0)} />
                  <Row label="Clients" value={String(redis.connected_clients ?? 0)} />
                  {/* Both of these are silent failure modes: evictions drop rate-limit state, and a
                      rejected connection surfaces as a random request error rather than an outage. */}
                  <Row label="Evicted keys" warn={(redis.evicted_keys ?? 0) > 0}
                    value={String(redis.evicted_keys ?? 0)} />
                  <Row label="Rejected connections" warn={(redis.rejected_connections ?? 0) > 0}
                    value={String(redis.rejected_connections ?? 0)} />
                </>
              )}
              {data.queue.available
                ? <Row label="Queue depth" warn={(data.queue.depth ?? 0) > 100} value={String(data.queue.depth ?? 0)} />
                : <p className="text-sm text-muted-foreground">Queue not collected: {data.queue.reason}</p>}
            </CardContent></Card>

            <Card><CardContent className="space-y-2 py-4">
              <p className="font-medium">Process</p>
              <Row label="Uptime" value={`${Math.floor(data.process.uptime_seconds / 3600)}h ${Math.floor((data.process.uptime_seconds % 3600) / 60)}m`} />
              <Row label="Peak memory" value={formatBytes(data.process.max_rss_kb * 1024)} />
              <Row label="CPU time" value={`${(data.process.cpu_user_seconds + data.process.cpu_system_seconds).toFixed(1)}s`} />
              {data.process.load_average && (
                <Row label={`Load average (${data.process.cpu_count} cores)`}
                  value={data.process.load_average.join(", ")}
                  warn={!!data.process.cpu_count && data.process.load_average[0] > data.process.cpu_count} />
              )}
              <Row label="Python" value={data.process.python} />
            </CardContent></Card>
          </>
        )}
      </div>
    </AppShell>
  );
}
