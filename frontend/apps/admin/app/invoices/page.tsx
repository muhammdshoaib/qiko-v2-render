"use client";

/**
 * Invoices and payment links.
 *
 * The last page in the console still rendering lists as stacks of cards: no column headers, nothing
 * sortable, no pagination, and a narrower page than everything around it. Consistency here is not
 * cosmetics. An operator who has learned that every list in this console has sortable headers and a
 * shareable URL loses that everywhere the moment one page does not, because they stop trusting the
 * pattern rather than noting the exception.
 *
 * The invoices list is the directory shell, so it inherits search, sort, pagination and URL state for
 * free. Payment links are NOT: they are looked up per email rather than browsed, so they get the table
 * without the directory chrome around them.
 */
import { Suspense, useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert, Badge, Button, Card, CardContent, DataTable, Input, SegmentedFilter, Skeleton, type Column,
} from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import {
  adminMe, createPaymentLink, formatMoney, listInvoices, listPaymentLinks,
  type Invoice, type PaymentLink,
} from "@/lib/api";

function formatPeriod(start: string | null, end: string | null) {
  if (!start || !end) return "-";
  const fmt = (d: string) => new Date(d).toLocaleDateString();
  return `${fmt(start)} - ${fmt(end)}`;
}

const invoiceColumns: Column<Invoice>[] = [
  {
    id: "invoice", header: "Invoice", rowHeader: true, sortable: true,
    cell: (row) => <span className="truncate font-medium">{row.number || row.stripe_invoice_id}</span>,
  },
  { id: "customer", header: "Customer", sortable: true, hideBelow: "md",
    cell: (row) => <span className="truncate">{row.customer_id}</span> },
  {
    id: "status", header: "Status", sortable: true,
    cell: (row) => (
      <Badge variant={row.status === "paid" ? "success" : "muted"}>{row.status}</Badge>
    ),
  },
  { id: "amount", header: "Amount", sortable: true, numeric: true,
    cell: (row) => formatMoney(row.amount_cents, row.currency || "USD") },
  { id: "period", header: "Period", sortable: true, hideBelow: "md",
    cell: (row) => formatPeriod(row.period_start, row.period_end) },
];

const linkColumns: Column<PaymentLink>[] = [
  {
    id: "customer_email", header: "Customer", rowHeader: true,
    cell: (row) => <span className="truncate">{row.customer_email}</span>,
  },
  { id: "amount_cents", header: "Amount", numeric: true,
    cell: (row) => formatMoney(row.amount_cents) },
  { id: "status", header: "Status",
    cell: (row) => <Badge variant={row.status === "paid" ? "success" : "muted"}>{row.status}</Badge> },
];

/** The lookup panel, above the directory. Kept as its own component so the directory below it stays a
 *  plain use of the shared shell rather than a special case. */
function PaymentLinks({ canManageBilling }: { canManageBilling: boolean }) {
  const [email, setEmail] = useState("");
  const [amount, setAmount] = useState("");
  const links = useQuery({
    queryKey: ["payment-links", email],
    queryFn: () => listPaymentLinks(email),
    enabled: email.includes("@"),
  });
  const createLink = useMutation({
    mutationFn: () => createPaymentLink(email, Math.round(Number(amount) * 100)),
    onSuccess: () => { setAmount(""); return links.refetch(); },
  });

  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div>
          <h2 className="font-semibold">Payment links</h2>
          <p className="text-xs text-muted-foreground">Looked up by customer email.</p>
        </div>

        {/* Capability, not role. A viewer granted manage_billing was shown "only a super-admin can do
            this" while the server would have accepted the write, which reads as a broken permission
            system rather than as a permission they lack. */}
        {!canManageBilling && (
          <p role="status" className="text-sm text-muted-foreground">
            Read-only access. Creating a payment link needs the Manage billing capability.
          </p>
        )}

        <div className="grid gap-3 sm:grid-cols-[1fr_10rem_auto]">
          <Input type="email" aria-label="Customer email" placeholder="Customer email"
            value={email} onChange={(event) => setEmail(event.target.value)} />
          {canManageBilling && (
            <>
              <Input type="number" min="0.5" step="0.01" aria-label="Amount" placeholder="Amount"
                value={amount} onChange={(event) => setAmount(event.target.value)} />
              <Button disabled={!email.includes("@") || Number(amount) <= 0 || createLink.isPending}
                onClick={() => createLink.mutate()}>
                {createLink.isPending ? "Creating..." : "Create link"}
              </Button>
            </>
          )}
        </div>

        {createLink.isError && <Alert tone="error">Payment link creation failed.</Alert>}
        {/* Success was silent before: the list refetched and nothing said the link had been made. */}
        {createLink.isSuccess && (
          <p role="status" className="text-sm text-success">Payment link created.</p>
        )}
        {links.isError && (
          <Alert tone="error">
            Couldn&apos;t load payment links.{" "}
            <button className="underline" onClick={() => links.refetch()}>Retry</button>
          </Alert>
        )}

        {/* Only once a lookup has actually run. Rendering the table's empty state before an email is
            entered would say "no payment links" about a customer nobody has named. */}
        {links.isSuccess && (
          <DataTable
            caption="Payment links for this customer"
            columns={linkColumns}
            rows={links.data}
            rowKey={(row) => row.session_id}
            actions={(row) => (
              <a className="text-sm underline" href={row.url} target="_blank" rel="noreferrer">
                Open link
              </a>
            )}
            empty={<p className="py-4 text-sm text-muted-foreground">No payment links for this email.</p>}
          />
        )}
        {links.isLoading && email.includes("@") && <Skeleton className="h-12 w-full" />}
      </CardContent>
    </Card>
  );
}

function InvoicesView() {
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "";
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const canManageBilling = me.data?.capabilities?.includes("manage_billing") ?? false;

  const setStatus = useCallback((value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set("status", value); else next.delete("status");
    next.delete("page");
    router.replace(`?${next.toString()}`, { scroll: false });
  }, [params, router]);

  return (
    <DirectoryPage<Invoice>
      title="Invoices"
      noun="invoices"
      searchLabel="Search invoices by id or customer"
      searchPlaceholder="Search by invoice or customer id..."
      queryKey="invoices"
      filterToken={status}
      onClearFilters={() => router.replace("?", { scroll: false })}
      fetchPage={(search, page, sort) => listInvoices(search, page, sort, status || undefined)}
      rowKey={(row) => row.stripe_invoice_id}
      columns={invoiceColumns}
      actions={(row) => (
        <div className="flex gap-2">
          {row.hosted_invoice_url && (
            <a className="text-sm underline" href={row.hosted_invoice_url} target="_blank" rel="noreferrer">Open</a>
          )}
          {row.invoice_pdf && (
            <a className="text-sm underline" href={row.invoice_pdf} target="_blank" rel="noreferrer">PDF</a>
          )}
        </div>
      )}
      filters={
        <div className="space-y-5">
          <PaymentLinks canManageBilling={canManageBilling} />
          <SegmentedFilter label="Filter by status" value={status}
            options={[{ value: "", label: "All" }, { value: "paid", label: "Paid" },
                      { value: "open", label: "Open" }, { value: "void", label: "Void" }]}
            onChange={setStatus} />
        </div>
      }
      emptyMessage={(filtered) => filtered
        ? "No invoices match this search or status."
        : "No invoices synced yet."}
    />
  );
}

export default function InvoicesPage() {
  return <Suspense fallback={null}><InvoicesView /></Suspense>;
}
