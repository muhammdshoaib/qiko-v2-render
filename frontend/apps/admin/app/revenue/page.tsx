"use client";

import { useQuery } from "@tanstack/react-query";
import { CreditCard, DollarSign, TrendingUp, Wallet } from "lucide-react";
import { Alert, Card, CardContent, Skeleton, TrendChart, type SeriesPoint } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { formatMoney, revenueReport } from "@/lib/api";

function Kpi({ label, value, icon: Icon }: {
  label: string; value: string; icon: typeof DollarSign;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 py-5">
        <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
          <Icon className="size-5" aria-hidden="true" />
        </span>
        <div>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
          <p className="text-sm text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function Panel({ title, subtitle, children }: {
  title: string; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div>
          <h2 className="font-semibold">{title}</h2>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

export default function RevenuePage() {
  const revenue = useQuery({ queryKey: ["revenue"], queryFn: revenueReport });

  if (revenue.isLoading) {
    return (
      <AppShell title="Revenue">
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </AppShell>
    );
  }

  if (revenue.isError || !revenue.data) {
    return (
      <AppShell title="Revenue">
        <Alert tone="error">Failed to load revenue report.</Alert>
      </AppShell>
    );
  }

  const data = revenue.data;
  const paidSeries: SeriesPoint[] = data.monthly.map((m) => ({
    label: m.month,
    value: m.paid_cents,
  }));
  const planMix: SeriesPoint[] = Object.entries(data.by_plan)
    .map(([plan, count]) => ({ label: plan, value: Number(count) }))
    .sort((a, b) => b.value - a.value);

  return (
    <AppShell title="Revenue">
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi label="Total Paid" value={formatMoney(data.total_paid_cents)} icon={DollarSign} />
          <Kpi label="Outstanding" value={formatMoney(data.outstanding_cents)} icon={Wallet} />
          <Kpi label="MRR" value={formatMoney(data.mrr_cents)} icon={TrendingUp} />
          <Kpi label="ARR" value={formatMoney(data.arr_cents)} icon={CreditCard} />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Panel title="Monthly paid revenue" subtitle="By invoice period start">
            {paidSeries.length > 0 ? (
              <TrendChart points={paidSeries} label="Monthly paid revenue" format={(v) => formatMoney(v)} />
            ) : (
              <p className="text-sm text-muted-foreground">No paid invoices yet.</p>
            )}
          </Panel>

          <Panel title="Active subscriptions" subtitle={`${data.active_subscriptions} total`}>
            {planMix.length > 0 ? (
              <TrendChart points={planMix} label="Active subscriptions" />
            ) : (
              <p className="text-sm text-muted-foreground">No active subscriptions.</p>
            )}
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
