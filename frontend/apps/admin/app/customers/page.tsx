"use client";

import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { CustomerDetailDialog } from "@/components/customer-detail-dialog";
import { formatMoney, adminMe, listCustomers, type Customer } from "@/lib/api";

const PAGE_SIZE = 20;

export default function CustomersPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const customers = useQuery({
    queryKey: ["customers", query, page],
    queryFn: () => listCustomers(query, page),
    enabled: me.isSuccess,
    // Keep the rows on screen while the next page loads instead of collapsing to skeletons.
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(search.trim()); setPage(1); }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const totalPages = Math.max(1, Math.ceil((customers.data?.total ?? 0) / PAGE_SIZE));

  return (
    <AppShell title="Customers">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Customers</h1>
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {me.isLoading || customers.isLoading ? "Loading total..." : customers.data ? `${customers.data.total} total` : "Total unavailable"}
            </p>
          </div>
          <label className="relative w-full sm:w-72">
            <span className="sr-only">Search customers by email</span>
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input className="min-h-11 pl-9" placeholder="Search by email..." value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
        </div>

        {me.isError && <Card><CardContent role="alert" className="py-6 text-sm text-destructive">Couldn&apos;t verify Admin access. <button className="underline" onClick={() => me.refetch()}>Retry</button></CardContent></Card>}
        {customers.isError && <Card><CardContent role="alert" className="py-6 text-sm text-destructive">Couldn&apos;t load customers. <button className="underline" onClick={() => customers.refetch()}>Retry</button></CardContent></Card>}

        <div className="space-y-2" aria-busy={customers.isFetching}>
          {customers.isLoading && [0, 1, 2].map((item) => <Skeleton key={item} className="h-20 w-full" />)}
          {customers.data?.items.map((customer: Customer) => (
            <Card key={customer.user_id}>
              <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-medium">{customer.email}</p>
                  <Badge variant="muted">{customer.plan}</Badge>
                </div>
                <div className="flex items-center justify-between gap-4 sm:justify-end">
                  <span className="text-sm font-semibold tabular-nums">{formatMoney(customer.earnings_cents)}</span>
                  <Button
                    variant="outline"
                    onClick={(event) => { opener.current = event.currentTarget; setSelected(customer.user_id); }}
                    aria-label={`View details for ${customer.email}`}
                  >View details</Button>
                </div>
              </CardContent>
            </Card>
          ))}
          {!customers.isLoading && customers.data?.items.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">{query ? "No customers match this search." : "No customers yet."}</p>
          )}
        </div>

        {!customers.isError && (customers.data?.total ?? 0) > 0 && (
          <nav aria-label="Customer pagination" className="flex items-center justify-between border-t border-border pt-4">
            <Button variant="outline" disabled={page <= 1 || customers.isFetching} onClick={() => setPage((value) => value - 1)}><ChevronLeft className="size-4" /> Previous</Button>
            <span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span>
            <Button variant="outline" disabled={page >= totalPages || customers.isFetching} onClick={() => setPage((value) => value + 1)}>Next <ChevronRight className="size-4" /></Button>
          </nav>
        )}
      </div>

      {me.data && (
        <CustomerDetailDialog
          customerId={selected}
          capabilities={me.data.capabilities}
          opener={opener.current}
          onClose={() => setSelected(null)}
        />
      )}
    </AppShell>
  );
}
