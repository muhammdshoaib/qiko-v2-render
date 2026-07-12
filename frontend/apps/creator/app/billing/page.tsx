"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Crown, ExternalLink, Zap } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { listPlans, subscriptionStatus, type BillingPlan } from "@/lib/api";

export default function BillingPage() {
  const [customerId, setCustomerId] = useState("");
  const [lookup, setLookup] = useState("");
  const sub = useQuery({
    queryKey: ["subscription", lookup],
    queryFn: () => subscriptionStatus(lookup),
    enabled: !!lookup,
  });
  const plans = useQuery({ queryKey: ["plans"], queryFn: listPlans });

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
            <Button variant="outline" className="border-white/20 text-white hover:bg-white/5">
              <ExternalLink className="size-4" /> View My Plan Details
            </Button>
          </div>

          <div className="mx-auto mb-8 max-w-2xl text-center">
            <h2 className="mb-2 text-3xl font-semibold text-foreground">Choose Your Plan</h2>
            <p className="text-muted-foreground">Start with Basic to test your digital worker, upgrade to Premium for custom fine-tuning, or go Enterprise for on-premise deployment.</p>
          </div>

          <div className="mx-auto mb-12 grid max-w-3xl justify-items-center gap-6 md:grid-cols-2">
            {plans.data?.map((p) => {
              const isEnterprise = p.name === "Enterprise";
              return (
                <Card key={p.id} className={cn("relative flex h-full w-full max-w-sm flex-col p-6", isEnterprise ? "border-white/10" : "border-primary")}>
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
                      {!isEnterprise && <Badge className="ml-auto">Current</Badge>}
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
                    <Button variant={isEnterprise ? "default" : "outline"} className="w-full">
                      {isEnterprise ? "Contact Us" : "Current Plan"}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Card className="mb-6">
            <CardHeader><CardTitle>Subscription status</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <div className="flex-1 space-y-1.5"><Label>Stripe customer id</Label>
                  <Input placeholder="cus_…" value={customerId} onChange={(e) => setCustomerId(e.target.value)} /></div>
                <div className="flex items-end"><Button onClick={() => setLookup(customerId)} disabled={!customerId}>Check</Button></div>
              </div>
              {sub.data && (
                <div className="flex items-center gap-2 text-sm">
                  Status: <Badge variant={sub.data.status === "active" ? "success" : "muted"}>{sub.data.status}</Badge>
                  {sub.data.plan && <span className="text-muted-foreground">plan: {sub.data.plan}</span>}
                </div>
              )}
            </CardContent>
          </Card>

          {plans.data && <FeatureComparison plans={plans.data} />}
        </div>
      </div>
    </AppShell>
  );
}

function FeatureComparison({ plans }: { plans: BillingPlan[] }) {
  const allFeatures = Array.from(new Set(plans.flatMap((p) => p.features)));
  return (
    <Card>
      <CardHeader><CardTitle>Feature Comparison</CardTitle></CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-2 font-medium">Feature</th>
              {plans.map((p) => <th key={p.id} className="py-2 font-medium">{p.name}</th>)}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-border/60">
              <td className="py-2">Digital Workers</td>
              {plans.map((p) => (
                <td key={p.id} className="py-2">{p.worker_limit < 0 ? "Custom / Scalable" : p.worker_limit}</td>
              ))}
            </tr>
            {allFeatures.map((f) => (
              <tr key={f} className="border-b border-border/60">
                <td className="py-2">{f}</td>
                {plans.map((p) => (
                  <td key={p.id} className="py-2">
                    {p.features.includes(f) || p.features.includes("Everything in Premium")
                      ? <Check className="size-4 text-success" /> : <span className="text-muted-foreground">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
