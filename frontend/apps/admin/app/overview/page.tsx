"use client";

/**
 * The platform overview.
 *
 * It showed three counts and a list of plan names. That is a page an operator opens once, learns
 * nothing from, and stops opening, which is worse than not having it: the landing page of a console
 * sets the expectation for everything behind it.
 *
 * WHAT IT SHOWS IS DECIDED BY WHAT THE READER CAN SEE. The overview is gated on view_customers, but
 * spend needs view_ai_cost, host figures need view_system_stats, and the activity feed needs
 * view_audit. Each block is fetched only when its capability is held, so a narrowed admin gets a
 * shorter page rather than a page full of errors, and no request is made that would be refused.
 *
 * Every panel says which window it covers. "Spend" with no period is a number nobody can act on, and
 * the previous page's counts had the same problem in a quieter way: "Customers 137" gives no sense of
 * whether that is growth or decline.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Activity, Bot, Building2, Coins, CreditCard, TrendingUp, Users,
} from "lucide-react";
import { Alert, BarList, Card, CardContent, Skeleton, TrendChart, type SeriesPoint } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  adminMe, aiCost, formatMoney, formatUsd, listTenants, overview, revenueReport, workerMonitoring,
  type Capability,
} from "@/lib/api";

const WINDOW_DAYS = 30;

function Kpi({ label, value, hint, icon: Icon, href }: {
  label: string; value: string | number; hint?: string;
  icon: typeof Users; href?: string;
}) {
  const body = (
    <CardContent className="flex items-center gap-4 py-5">
      <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        <p className="truncate text-sm text-muted-foreground">{label}</p>
        {/* The qualifier belongs on the number, not in a footnote. A count with no period or scope is
            the kind of figure that gets quoted in a meeting and turns out to mean something else. */}
        {hint && <p className="truncate text-xs text-muted-foreground">{hint}</p>}
      </div>
    </CardContent>
  );
  // Every figure leads to the page that explains it. A dashboard that only states numbers makes the
  // reader go and find the list themselves, which is the step they were trying to skip.
  return href
    ? <Card className="transition-colors hover:border-primary/40"><Link href={href} className="block">{body}</Link></Card>
    : <Card>{body}</Card>;
}

function Panel({ title, subtitle, children, action }: {
  title: string; subtitle?: string; children: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <h2 className="font-semibold">{title}</h2>
            {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          {action}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

export default function OverviewPage() {
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const can = (capability: Capability) => me.data?.capabilities?.includes(capability) ?? false;

  const ov = useQuery({ queryKey: ["overview"], queryFn: overview, enabled: me.isSuccess });
  // Only the first page: this is the top of a ranking, not a directory. Pulling everything to compute a
  // total the server already gives would be slower and no more correct.
  const tenants = useQuery({
    queryKey: ["overview-tenants"],
    queryFn: () => listTenants("", 1, { sort: "earnings", order: "desc" }),
    enabled: me.isSuccess && can("view_customers"),
  });
  const workers = useQuery({
    queryKey: ["overview-workers", WINDOW_DAYS],
    queryFn: () => workerMonitoring(WINDOW_DAYS, 1, undefined, { sort: "calls", order: "desc" }),
    enabled: me.isSuccess && can("view_customers"),
  });
  const spend = useQuery({
    queryKey: ["overview-spend", WINDOW_DAYS],
    queryFn: () => aiCost(WINDOW_DAYS),
    // Not fetched at all without the capability, rather than fetched and hidden: a request that would
    // be refused is a 403 in the log and a red herring for whoever reads it next.
    enabled: me.isSuccess && can("view_ai_cost"),
  });
  const revenue = useQuery({
    queryKey: ["overview-revenue"],
    queryFn: revenueReport,
    enabled: me.isSuccess && can("view_customers"),
  });

  const loading = me.isLoading || (me.isSuccess && ov.isLoading);

  const spendByDay: SeriesPoint[] = Object.entries(spend.data?.day ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, totals]) => ({
      label: new Date(day).toLocaleDateString(undefined, { day: "2-digit", month: "short" }),
      value: totals.cost_nano_usd,
    }));
  const planMix: SeriesPoint[] = Object.entries(ov.data?.by_plan ?? {})
    .map(([plan, count]) => ({ label: plan, value: Number(count) }))
    .sort((a, b) => b.value - a.value);
  const topTenants: SeriesPoint[] = (tenants.data?.items ?? [])
    .filter((t) => t.earnings_cents > 0).slice(0, 5)
    .map((t) => ({ label: t.email, value: t.earnings_cents }));
  const busiestWorkers: SeriesPoint[] = (workers.data?.items ?? [])
    .filter((w) => w.calls > 0).slice(0, 5)
    .map((w) => ({ label: w.name, value: w.calls }));

  const activeWorkers = (workers.data?.items ?? []).filter((w) => w.calls > 0).length;

  return (
    <AppShell title="Overview">
      <div className="mx-auto max-w-6xl space-y-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>
            Platform Overview
          </h1>
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
            {loading ? "Loading platform metrics..."
              : ov.isError ? "Overview unavailable."
                : `Activity and spend over the last ${WINDOW_DAYS} days.`}
          </p>
        </div>

        {ov.isError && (
          <Alert tone="error">
            Overview unavailable.{" "}
            <button className="underline" onClick={() => ov.refetch()}>Retry</button>
          </Alert>
        )}

        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
          </div>
        ) : ov.data && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Kpi label="Customers" value={ov.data.customers_total} icon={Users} href="/customers" />
              <Kpi label="Active subscriptions" value={ov.data.active_subscriptions}
                hint={`${planMix.length} ${planMix.length === 1 ? "plan" : "plans"} in use`}
                icon={CreditCard} href="/subscriptions" />
              {can("view_customers") ? (
                <Kpi label="Revenue" value={revenue.data ? formatMoney(revenue.data.total_paid_cents) : "-"}
                  icon={TrendingUp} href="/revenue" />
              ) : (
                <Kpi label="Tenants" value={tenants.data?.total ?? "-"} icon={Building2} href="/tenants" />
              )}
              {can("view_ai_cost") ? (
                <Kpi label="AI spend" value={spend.data ? formatUsd(spend.data.totals.cost_nano_usd) : "-"}
                  hint={`last ${WINDOW_DAYS} days`} icon={Coins} href="/ai-cost" />
              ) : (
                <Kpi label="Workers active" value={activeWorkers}
                  hint={`used in the last ${WINDOW_DAYS} days`} icon={Bot} href="/monitoring" />
              )}
            </div>

            {can("view_ai_cost") && (
              <Panel title="AI spend per day" subtitle={`Last ${WINDOW_DAYS} days, all tenants`}
                action={<Link href="/ai-cost" className="text-sm underline decoration-dotted">Break down</Link>}>
                {spend.isLoading
                  ? <Skeleton className="h-[120px] w-full" />
                  : <TrendChart points={spendByDay} label={`AI spend per day, last ${WINDOW_DAYS} days`}
                      format={(v) => formatUsd(v)} />}
              </Panel>
            )}

            <div className="grid gap-5 lg:grid-cols-2">
              <Panel title="Subscriptions by plan"
                subtitle={`${ov.data.active_subscriptions} active`}>
                {/* Scaled against the total rather than the largest plan, so the bars read as a share of
                    the base rather than as a ranking against each other. */}
                <BarList items={planMix} label="Subscriptions by plan"
                  max={ov.data.active_subscriptions || undefined}
                  emptyMessage="No active subscriptions." />
              </Panel>

              {can("view_customers") && (
                <Panel title="Highest earning tenants" subtitle="Lifetime, top five"
                  action={<Link href="/tenants" className="text-sm underline decoration-dotted">All tenants</Link>}>
                  {tenants.isLoading
                    ? <Skeleton className="h-24 w-full" />
                    : <BarList items={topTenants} label="Highest earning tenants"
                        format={(v) => formatMoney(v)}
                        emptyMessage="No earnings recorded yet." />}
                </Panel>
              )}

              {can("view_customers") && (
                <Panel title="Busiest workers" subtitle={`By model calls, last ${WINDOW_DAYS} days`}
                  action={<Link href="/monitoring" className="text-sm underline decoration-dotted">Monitoring</Link>}>
                  {workers.isLoading
                    ? <Skeleton className="h-24 w-full" />
                    : <BarList items={busiestWorkers} label="Busiest workers"
                        format={(v) => `${new Intl.NumberFormat().format(v)} calls`}
                        emptyMessage="No worker activity in this window." />}
                </Panel>
              )}

              {can("view_ai_cost") && (
                <Panel title="Spend by model" subtitle={`Last ${WINDOW_DAYS} days`}>
                  {spend.isLoading
                    ? <Skeleton className="h-24 w-full" />
                    : <BarList
                        items={Object.entries(spend.data?.model ?? {})
                          .map(([model, t]) => ({ label: model, value: t.cost_nano_usd }))
                          .sort((a, b) => b.value - a.value).slice(0, 5)}
                        label="Spend by model" format={(v) => formatUsd(v)}
                        emptyMessage="No priced model calls in this window." />}
                </Panel>
              )}
            </div>

            {/* Named rather than left as a shorter page with no explanation: an operator who cannot see
                spend should know the figures exist, not conclude the platform has none. */}
            {!can("view_ai_cost") && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Activity className="size-4" aria-hidden="true" />
                Spend figures need the View AI cost capability.
              </p>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
