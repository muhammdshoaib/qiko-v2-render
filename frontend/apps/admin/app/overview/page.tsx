"use client";

import { useQuery } from "@tanstack/react-query";
import { Users, CreditCard, Layers } from "lucide-react";
import { Badge, Card, CardContent, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { overview } from "@/lib/api";

function Kpi({ label, value, icon: Icon }: { label: string; value: string | number; icon: any }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 py-5">
        <span className="grid size-11 place-items-center rounded-lg bg-accent text-accent-foreground"><Icon className="size-5" /></span>
        <div>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
          <p className="text-sm text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export default function OverviewPage() {
  const ov = useQuery({ queryKey: ["overview"], queryFn: overview });

  return (
    <AppShell title="Overview">
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Platform Overview</h1>
          <p className="text-sm text-muted-foreground">Key metrics across the platform.</p>
        </div>

        {ov.isError && <Card><CardContent role="alert" className="py-6 text-sm text-destructive">Overview unavailable. <button className="underline" onClick={() => ov.refetch()}>Retry</button></CardContent></Card>}

        {ov.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
        ) : ov.data && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Kpi label="Customers" value={ov.data.customers_total} icon={Users} />
              <Kpi label="Active subscriptions" value={ov.data.active_subscriptions} icon={CreditCard} />
              <Kpi label="Plans in use" value={Object.keys(ov.data.by_plan).length} icon={Layers} />
            </div>
            <Card>
              <CardContent className="space-y-2 pt-6">
                <h3 className="text-sm font-medium text-muted-foreground">Subscriptions by plan</h3>
                {Object.entries(ov.data.by_plan).length === 0 && <p className="text-sm text-muted-foreground">No active subscriptions.</p>}
                {Object.entries(ov.data.by_plan).map(([plan, n]) => (
                  <div key={plan} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                    <Badge variant="muted">{plan}</Badge>
                    <span className="text-sm font-semibold tabular-nums">{n}</span>
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
