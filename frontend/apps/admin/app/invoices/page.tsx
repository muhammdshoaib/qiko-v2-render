"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { adminMe, createPaymentLink, formatMoney, listInvoices, listPaymentLinks, type Invoice } from "@/lib/api";

export default function InvoicesPage() {
  const invoices = useQuery({ queryKey: ["invoices"], queryFn: listInvoices });
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const [email, setEmail] = useState("");
  const [amount, setAmount] = useState("");
  const links = useQuery({ queryKey: ["payment-links", email], queryFn: () => listPaymentLinks(email), enabled: email.includes("@") });
  const createLink = useMutation({
    mutationFn: () => createPaymentLink(email, Math.round(Number(amount) * 100)),
    onSuccess: () => { setAmount(""); return links.refetch(); },
  });
  // Capability, not role. A viewer granted manage_billing was shown "only a super-admin can do this"
  // while the server would have accepted the write, which reads as a broken permission system.
  const canManageBilling = me.data?.capabilities?.includes("manage_billing") ?? false;

  return (
    <AppShell title="Invoices">
      <div className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Invoices & Payment Links</h1>
        <Card>
          <CardContent className="space-y-3 py-5">
            <h2 className="font-semibold">Payment links</h2>
            {!canManageBilling && (
              <p role="status" className="text-sm text-muted-foreground">
                Read-only access. Creating a payment link needs the Manage billing capability.
              </p>
            )}
            {canManageBilling && (
              <div className="grid gap-3 sm:grid-cols-[1fr_10rem_auto]">
                <Input type="email" aria-label="Customer email" placeholder="Customer email"
                  value={email} onChange={(event) => setEmail(event.target.value)} />
                <Input type="number" min="0.5" step="0.01" aria-label="Amount" placeholder="Amount"
                  value={amount} onChange={(event) => setAmount(event.target.value)} />
                <Button disabled={!email.includes("@") || Number(amount) <= 0 || createLink.isPending}
                  onClick={() => createLink.mutate()}>
                  {createLink.isPending ? "Creating..." : "Create link"}
                </Button>
              </div>
            )}
            {createLink.isError && (
              <p role="alert" className="text-sm text-destructive">Payment link creation failed.</p>
            )}
            {/* Success was previously silent: the list refetched and nothing said the link was made. */}
            {createLink.isSuccess && (
              <p role="status" className="text-sm text-success">Payment link created.</p>
            )}
            {/* The links query had no error branch at all, so a failed lookup looked like "no links". */}
            {links.isError && (
              <p role="alert" className="text-sm text-destructive">
                Couldn&apos;t load payment links.{" "}
                <button className="underline" onClick={() => links.refetch()}>Retry</button>
              </p>
            )}
            {links.isSuccess && links.data.length === 0 && (
              <p className="text-sm text-muted-foreground">No payment links for this email.</p>
            )}
            {links.data?.map((link) => (
              <div key={link.session_id}
                className="flex flex-col gap-1 rounded border p-3 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-sm">
                  {link.customer_email} &middot; {formatMoney(link.amount_cents)} &middot; {link.status}
                </span>
                <a className="text-sm underline" href={link.url} target="_blank" rel="noreferrer">Open link</a>
              </div>
            ))}
          </CardContent>
        </Card>
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
                  <span className="text-sm font-semibold tabular-nums">{formatMoney(inv.amount_cents)}</span>
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
