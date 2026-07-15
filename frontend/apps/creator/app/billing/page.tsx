"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Crown, ExternalLink, X, Zap } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { listPlans } from "@/lib/api";

export default function BillingPage() {
  const plans = useQuery({ queryKey: ["plans"], queryFn: listPlans });

  return (
    <AppShell title="Billing">
      <div className="p-6 lg:p-8">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="mb-2 text-center text-2xl font-bold text-white lg:text-left lg:text-3xl" style={{ fontFamily: "var(--font-display)" }}>
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
                <Card key={p.id} className="relative flex h-full w-full max-w-sm flex-col border-white/[0.06] bg-white/[0.015] p-6">
                  {isEnterprise && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">
                      Most Popular
                    </span>
                  )}
                  <CardContent className="flex h-full flex-col p-0">
                    <div className="mb-4 flex items-center gap-3">
                      <span className={cn("grid size-10 shrink-0 place-items-center rounded-lg", isEnterprise ? "bg-violet-500/20 text-violet-400" : "bg-indigo-500/20 text-indigo-400")}>
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
