"use client";

import { useQuery } from "@tanstack/react-query";
import { Badge, Card, CardContent, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { listInvoices, type Invoice } from "@/lib/api";

export default function InvoicesPage() {
  const invoices = useQuery({ queryKey: ["invoices"], queryFn: listInvoices });

  return (
    <AppShell title="Invoices">
      <div className="mx-auto max-w-4xl space-y-6">
        <h2 className="text-2xl font-semibold tracking-tight">Invoices</h2>
        {invoices.isError && <Card><CardContent className="py-6 text-sm text-destructive">Not authorized (admin role required).</CardContent></Card>}
        <div className="space-y-2">
          {invoices.isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
          {invoices.data?.map((inv: Invoice) => (
            <Card key={inv.stripe_invoice_id}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-medium">{inv.stripe_invoice_id}</p>
                  <p className="text-xs text-muted-foreground">{inv.customer_id}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={inv.status === "paid" ? "success" : "muted"}>{inv.status}</Badge>
                  <span className="text-sm font-semibold tabular-nums">${(inv.amount_cents / 100).toFixed(2)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
          {invoices.data?.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">No invoices yet.</p>}
        </div>
      </div>
    </AppShell>
  );
}
