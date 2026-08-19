"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, Crown, ExternalLink, Loader2, X, Zap } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { billingPortal, listPlans, startCheckout, subscriptionStatus, type BillingPlan } from "@/lib/api";

export default function BillingPage() {
  const plans = useQuery({ queryKey: ["plans"], queryFn: listPlans });
  // The subscription subject is the authed tenant (derived server-side); used to mark the plan the
  // caller is actually on so the CTA reads "Current Plan" only for that plan, not every paid tier.
  const sub = useQuery({ queryKey: ["subscription"], queryFn: subscriptionStatus, retry: false });
  const activeSub = sub.data && (sub.data.status === "active" || sub.data.status === "trialing");
  const currentPlanName = activeSub ? (sub.data?.plan ?? "").trim().toLowerCase() : "";

  const portal = useMutation({
    mutationFn: billingPortal,
    onSuccess: (res) => { if (res?.url) window.location.href = res.url; },
  });
  const checkout = useMutation({
    mutationFn: (p: BillingPlan) => startCheckout(p.key, p.price_id),
    onSuccess: (res) => { if (res?.url) window.location.href = res.url; },
  });

  return (
    <AppShell title="Billing">
      <div className="p-6 lg:p-8">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="mb-2 text-center text-2xl font-bold lg:text-left lg:text-3xl" style={{
                fontFamily: "var(--font-display)",
                background: "linear-gradient(135deg, #fff 0%, #6366F1 50%, #22D3EE 100%)",
                WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent",
              }}>
                Plans &amp; Pricing
              </h1>
              <p className="text-slate-400">Choose the right plan for your needs</p>
            </div>
            <Button variant="outline" className="border-white/20 text-white hover:bg-white/5"
              disabled={portal.isPending} onClick={() => portal.mutate()}>
              {portal.isPending ? <Loader2 className="size-4 animate-spin" /> : <ExternalLink className="size-4" />} View My Plan Details
            </Button>
          </div>

          {portal.isError && (
            <p className="mb-6 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
              <AlertTriangle className="size-4 shrink-0" /> Couldn&apos;t open the billing portal. Please try again.
            </p>
          )}
          {checkout.isError && (
            <p className="mb-6 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
              <AlertTriangle className="size-4 shrink-0" /> Couldn&apos;t start checkout. Please try again.
            </p>
          )}

          <div className="mx-auto mb-8 max-w-2xl text-center">
            <h2 className="mb-2 text-3xl font-semibold text-foreground">Choose Your Plan</h2>
            <p className="text-muted-foreground">Start with Basic to test your digital worker, upgrade to Premium for custom fine-tuning, or go Enterprise for on-premise deployment.</p>
          </div>

          {plans.isLoading ? (
            <div className="mx-auto mb-12 grid max-w-3xl gap-6 md:grid-cols-2">
              {[0, 1].map((i) => (
                <div key={i} className="h-80 w-full max-w-sm animate-pulse rounded-xl border border-white/[0.06] bg-white/[0.02]" />
              ))}
            </div>
          ) : plans.isError ? (
            <div className="mx-auto mb-12 max-w-2xl">
              <p className="flex items-center justify-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-6 text-sm text-red-300">
                <AlertTriangle className="size-4 shrink-0" /> Couldn&apos;t load plans.
                <button onClick={() => plans.refetch()} className="ml-1 font-semibold underline">Retry</button>
              </p>
            </div>
          ) : (plans.data?.length ?? 0) === 0 ? (
            <p className="mx-auto mb-12 max-w-2xl text-center text-sm text-muted-foreground">No plans are available right now.</p>
          ) : (
            <div className="mx-auto mb-12 grid max-w-3xl justify-items-center gap-6 md:grid-cols-2">
              {plans.data?.map((p) => {
                const isEnterprise = p.key === "enterprise";
                const isCurrent = !!currentPlanName && p.key === currentPlanName;
                const checkingOut = checkout.isPending && checkout.variables?.id === p.id;
                return (
                  <Card key={p.id} className="relative flex h-full w-full max-w-sm flex-col border-white/[0.06] bg-white/[0.015] p-6">
                    {isEnterprise && (
                      <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">
                        Most Popular
                      </span>
                    )}
                    <CardContent className="flex h-full flex-col p-0">
                      <div className="mb-4 flex items-center gap-3">
                        <span className={cn("grid size-10 shrink-0 place-items-center rounded-lg", isEnterprise ? "bg-violet-500/20 text-violet-400" : "bg-blue-500/20 text-blue-400")}>
                          {isEnterprise ? <Crown className="size-6" /> : <Zap className="size-6" />}
                        </span>
                        <div>
                          <h3 className="font-semibold text-foreground">{p.name}</h3>
                          <p className="line-clamp-2 text-xs text-muted-foreground">{p.name} monthly plan</p>
                        </div>
                        {isCurrent && <Badge className="ml-auto">Current</Badge>}
                      </div>
                      <div className="mb-6 flex items-baseline gap-1">
                        <span className="text-4xl font-bold text-foreground">{p.display_price}</span>
                        {p.display_price !== "Custom Pricing" && <span className="text-muted-foreground">/month</span>}
                      </div>
                      <ul className="mb-6 flex-1 space-y-3">
                        {p.features.map((f) => (
                          <li key={f} className="flex items-center gap-3 text-sm">
                            <Check className="size-5 shrink-0 text-emerald-400" />
                            <span className="text-muted-foreground">{f}</span>
                          </li>
                        ))}
                      </ul>
                      {isEnterprise ? (
                        <Button variant="default" className="w-full" onClick={() => (window.location.href = "/labs")}>
                          Contact Us
                        </Button>
                      ) : isCurrent ? (
                        <Button variant="outline" className="w-full" disabled>Current Plan</Button>
                      ) : (
                        <Button variant="outline" className="w-full" disabled={checkout.isPending} onClick={() => checkout.mutate(p)}>
                          {checkingOut ? <Loader2 className="size-4 animate-spin" /> : null} Choose {p.name}
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}

          <FeatureComparison />
        </div>
      </div>
    </AppShell>
  );
}

// Matches TierFeatureComparison.tsx on stage-app.qiko.ai exactly: fixed Premium/Enterprise rows
// (not derived from each plan's free-text `features` list, which produced duplicated/garbled
// rows like a second "3 Digital Workers" line and a stray "Everything in Premium" row).
const FEATURE_ROWS: { label: string; premium: string | boolean; enterprise: string | boolean }[] = [
  { label: "Digital Workers", premium: "3", enterprise: "Custom / Scalable" },
  { label: "Chats", premium: "Unlimited", enterprise: "Unlimited" },
  { label: "Training Rules", premium: "Unlimited", enterprise: "Unlimited" },
  { label: "Knowledge Base Auto-Learning", premium: true, enterprise: true },
  { label: "Calendly Integration", premium: true, enterprise: true },
  { label: "Voice Call Enablement", premium: true, enterprise: true },
  { label: "Website Chat Embed", premium: true, enterprise: true },
  { label: "Custom Knowledge Training", premium: true, enterprise: true },
  { label: "Custom Model Build (IP Owned)", premium: false, enterprise: true },
  { label: "Data Tagging & AI Pipeline", premium: false, enterprise: true },
  { label: "On-Prem Deployment", premium: false, enterprise: true },
  { label: "Full Model Export (GGUF)", premium: false, enterprise: true },
  { label: "Dedicated account manager.", premium: false, enterprise: true },
];

function FeatureCell({ value }: { value: string | boolean }) {
  if (typeof value === "string") return <span className="text-sm text-foreground">{value}</span>;
  return value
    ? <Check className="inline-block size-5 text-emerald-400" />
    : <X className="inline-block size-5 text-muted-foreground/50" />;
}

function FeatureComparison() {
  return (
    <Card>
      <CardHeader><CardTitle>Feature Comparison</CardTitle></CardHeader>
      <CardContent>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="py-3 px-4 text-left text-sm font-medium text-muted-foreground">Feature</th>
              <th className="py-3 px-4 text-center text-sm font-medium text-primary">Premium</th>
              <th className="py-3 px-4 text-center text-sm font-medium text-purple-400">Enterprise</th>
            </tr>
          </thead>
          <tbody>
            {FEATURE_ROWS.map((row, i) => (
              <tr key={row.label} className={i % 2 === 0 ? "bg-white/[0.02]" : ""}>
                <td className="py-3 px-4"><span className="text-sm text-foreground">{row.label}</span></td>
                <td className="py-3 px-4 text-center"><FeatureCell value={row.premium} /></td>
                <td className="py-3 px-4 text-center"><FeatureCell value={row.enterprise} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
