"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
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
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Plans &amp; Pricing</h1>
          <p className="text-sm text-muted-foreground">Choose the right plan for your needs</p>
        </div>

        <Card>
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

        <div className="grid gap-4 sm:grid-cols-2">
          {plans.data?.map((p) => (
            <Card key={p.id} className={cn(p.name === "Enterprise" && "ring-2 ring-primary")}>
              <CardContent className="space-y-3 pt-6">
                <div className="flex items-baseline justify-between">
                  <p className="font-semibold">{p.name}</p>
                  {p.name === "Enterprise" && <Badge>Most Popular</Badge>}
                </div>
                <p className="text-2xl font-bold">
                  {p.display_price}
                  {p.display_price !== "Custom Pricing" && <span className="text-sm font-normal text-muted-foreground">/month</span>}
                </p>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  {p.features.map((f) => <li key={f} className="flex items-center gap-2"><Check className="size-4 text-success" /> {f}</li>)}
                </ul>
                <Button variant={p.name === "Enterprise" ? "outline" : "default"} className="w-full">
                  {p.name === "Enterprise" ? "Contact Us" : "Choose Plan"}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>

        {plans.data && <FeatureComparison plans={plans.data} />}
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
