"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { subscriptionStatus } from "@/lib/api";

const PLANS = [
  { id: "free", name: "Free", price: "$0", features: ["1 worker", "Community support"] },
  { id: "pro", name: "Pro", price: "$49", features: ["5 workers", "Priority support", "Channels"] },
  { id: "enterprise", name: "Enterprise", price: "Custom", features: ["Unlimited workers", "SSO", "SLA"] },
];

export default function BillingPage() {
  const [customerId, setCustomerId] = useState("");
  const [lookup, setLookup] = useState("");
  const sub = useQuery({
    queryKey: ["subscription", lookup],
    queryFn: () => subscriptionStatus(lookup),
    enabled: !!lookup,
  });

  return (
    <AppShell title="Billing">
      <div className="mx-auto max-w-3xl space-y-6">
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

        <div>
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">Plans</h3>
          <div className="grid gap-4 sm:grid-cols-3">
            {PLANS.map((p) => (
              <Card key={p.id} className={cn(p.id === "pro" && "ring-2 ring-primary")}>
                <CardContent className="space-y-3 pt-6">
                  <div className="flex items-baseline justify-between">
                    <p className="font-semibold">{p.name}</p>
                    {p.id === "pro" && <Badge>Popular</Badge>}
                  </div>
                  <p className="text-2xl font-bold">{p.price}<span className="text-sm font-normal text-muted-foreground">/mo</span></p>
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    {p.features.map((f) => <li key={f} className="flex items-center gap-2"><Check className="size-4 text-[hsl(var(--success))]" /> {f}</li>)}
                  </ul>
                  <Button variant={p.id === "pro" ? "default" : "outline"} className="w-full">
                    {p.id === "enterprise" ? "Contact sales" : "Choose plan"}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
