"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { adminMe, createPaymentLink, listInvoices, listPaymentLinks, type Invoice } from "@/lib/api";

export default function InvoicesPage() {
  const invoices = useQuery({ queryKey: ["invoices"], queryFn: listInvoices });
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const [email, setEmail] = useState("");
  const [amount, setAmount] = useState("");
  const links = useQuery({ queryKey: ["payment-links", email], queryFn: () => listPaymentLinks(email), enabled: email.includes("@") });
  const createLink = useMutation({ mutationFn: () => createPaymentLink(email, Math.round(Number(amount) * 100)), onSuccess: () => links.refetch() });

  return (
    <AppShell title="Invoices">
      <div className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Invoices & Payment Links</h1>
        <Card><CardContent className="space-y-3 py-5"><h2 className="font-semibold">Payment links</h2>{me.data?.role === "viewer" && <p role="status" className="text-sm text-muted-foreground">Read-only access. Only a super-admin can create payment links.</p>}{me.data?.role === "super_admin" && <div className="grid gap-3 sm:grid-cols-[1fr_10rem_auto]"><Input type="email" aria-label="Customer email" placeholder="Customer email" value={email} onChange={(event) => setEmail(event.target.value)} /><Input type="number" min="0.5" step="0.01" aria-label="Amount" placeholder="Amount" value={amount} onChange={(event) => setAmount(event.target.value)} /><Button disabled={!email.includes("@") || Number(amount) <= 0 || createLink.isPending} onClick={() => createLink.mutate()}>Create link</Button></div>}{createLink.isError && <p role="alert" className="text-sm text-destructive">Payment link creation failed.</p>}{links.data?.map((link) => <div key={link.session_id} className="flex flex-col gap-1 rounded border p-3 sm:flex-row sm:items-center sm:justify-between"><span className="text-sm">{link.customer_email} · ${(link.amount_cents / 100).toFixed(2)} · {link.status}</span><a className="text-sm underline" href={link.url} target="_blank" rel="noreferrer">Open link</a></div>)}</CardContent></Card>
        {invoices.isError && <Card><CardContent role="alert" className="py-6 text-sm text-destructive">Invoices unavailable. <button className="underline" onClick={() => invoices.refetch()}>Retry</button></CardContent></Card>}
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
