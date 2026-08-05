"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { aiCost, formatUsd, type UsageTotals } from "@/lib/api";

const WINDOWS = [7, 30, 90] as const;

function Breakdown({ title, rows }: { title: string; rows: Record<string, UsageTotals> }) {
  const entries = Object.entries(rows).sort((a, b) => b[1].cost_nano_usd - a[1].cost_nano_usd);
  return (
    <Card>
      <CardContent className="space-y-2 py-4">
        <p className="font-medium">{title}</p>
        {entries.length === 0 && <p className="text-sm text-muted-foreground">No activity yet.</p>}
        {entries.map(([key, totals]) => (
          <div key={key} className="flex items-center justify-between gap-3 text-sm">
            <span className="min-w-0 truncate">{key}</span>
            <span className="flex shrink-0 items-center gap-3 text-muted-foreground">
              <span>{totals.calls} {totals.calls === 1 ? "call" : "calls"}</span>
              <span className="tabular-nums text-foreground">{formatUsd(totals.cost_nano_usd)}</span>
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function AiCostPage() {
  const [days, setDays] = useState<number>(30);
  const cost = useQuery({ queryKey: ["ai-cost", days], queryFn: () => aiCost(days) });
  const data = cost.data;

  return (
    <AppShell title="AI Cost">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>AI Cost</h1>
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {cost.isLoading ? "Loading spend..."
                : data ? `${formatUsd(data.totals.cost_nano_usd)} over ${data.window_days} days`
                : "Spend unavailable"}
            </p>
          </div>
          <div role="group" aria-label="Time window" className="flex gap-2">
            {WINDOWS.map((option) => (
              <Button key={option} className="min-h-11" aria-pressed={days === option}
                variant={days === option ? "default" : "outline"} onClick={() => setDays(option)}>
                {option}d
              </Button>
            ))}
          </div>
        </div>

        {cost.isError && (
          <Card><CardContent role="alert" className="py-6 text-sm text-destructive">
            Couldn&apos;t load AI spend.{" "}
            <button className="underline" onClick={() => cost.refetch()}>Retry</button>
          </CardContent></Card>
        )}

        {cost.isLoading && [0, 1, 2].map((index) => <Skeleton key={index} className="h-28 w-full" />)}

        {data && (
          <>
            <Card><CardContent className="grid gap-4 py-4 sm:grid-cols-4">
              <Summary label="Spend" value={formatUsd(data.totals.cost_nano_usd)} />
              <Summary label="Calls" value={data.totals.calls.toLocaleString()} />
              <Summary label="Input tokens" value={data.totals.input_tokens.toLocaleString()} />
              <Summary label="Output tokens" value={data.totals.output_tokens.toLocaleString()} />
            </CardContent></Card>

            {data.totals.unpriced_calls > 0 && (
              // Saying this out loud matters: the headline number understates reality whenever a model
              // has no published rate, and a silently low total is worse than an obviously incomplete one.
              <Card><CardContent role="status" className="py-4 text-sm text-muted-foreground">
                {data.totals.unpriced_calls} {data.totals.unpriced_calls === 1 ? "call was" : "calls were"} made
                against a model with no published rate, so the totals above understate actual spend.
              </CardContent></Card>
            )}

            <Breakdown title="By tenant" rows={data.tenant} />
            <Breakdown title="By model" rows={data.model} />
            <Breakdown title="By operation" rows={data.operation} />
            <Breakdown title="By day" rows={data.day} />
          </>
        )}
      </div>
    </AppShell>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}
