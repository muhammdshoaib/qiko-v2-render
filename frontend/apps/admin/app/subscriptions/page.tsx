"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { formatMoney, listCustomers } from "@/lib/api";

// Must match pagination.PAGE_SIZE on the server.
const PAGE_SIZE = 20;

export default function SubscriptionsPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  // Debounced, like every other list. Without this the query key changed on every keystroke, firing a
  // request per character.
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const customers = useQuery({
    queryKey: ["subscriptions", query, page],
    // This page never sent a page, so only the first twenty accounts were ever reachable.
    queryFn: () => listCustomers(query, page),
    placeholderData: keepPreviousData,
  });

  const pageCount = customers.data ? Math.max(1, Math.ceil(customers.data.total / PAGE_SIZE)) : 1;
  const shown = customers.data?.items.length ?? 0;
  const firstOnPage = shown === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;

  return (
    <AppShell title="Subscriptions">
      <div className="mx-auto max-w-4xl space-y-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>Subscriptions</h1>
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
            {customers.isLoading ? "Loading subscriptions..."
              : customers.data
                ? `Showing ${firstOnPage}-${(page - 1) * PAGE_SIZE + shown} of ${customers.data.total} accounts`
                : "Subscriptions unavailable"}
          </p>
        </div>

        <label className="block">
          <span className="sr-only">Search subscriptions by customer email</span>
          <Input placeholder="Search by customer email" value={search}
            onChange={(event) => setSearch(event.target.value)} />
        </label>

        {customers.isError && (
          <Card><CardContent role="alert" className="py-6 text-sm text-destructive">
            Subscriptions unavailable.{" "}
            <button className="underline" onClick={() => customers.refetch()}>Retry</button>
          </CardContent></Card>
        )}

        <div className="space-y-2" aria-busy={customers.isFetching}>
          {customers.isLoading && [0, 1, 2].map((index) => <Skeleton key={index} className="h-16 w-full" />)}
          {customers.data?.items.map((customer) => (
            <Card key={customer.user_id}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
                <div className="min-w-0">
                  <p className="truncate font-medium">{customer.email}</p>
                  <p className="truncate text-xs text-muted-foreground">{customer.user_id}</p>
                </div>
                <div className="flex items-center gap-3">
                  {/* The plan the directory reports is already derived from the ACTIVE subscription
                      (a lapsed one reads as "free"), so it is the subscription state, not a guess. */}
                  <Badge variant={customer.plan === "free" ? "muted" : "default"}>{customer.plan}</Badge>
                  <span className="text-sm font-semibold tabular-nums">{formatMoney(customer.earnings_cents)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
          {customers.data?.items.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {query ? "No accounts match this search." : "No accounts yet."}
            </p>
          )}
        </div>

        {pageCount > 1 && (
          <nav aria-label="Subscription pagination" className="flex items-center justify-between gap-3">
            <Button variant="outline" className="min-h-11" disabled={page <= 1 || customers.isFetching}
              onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</Button>
            <span className="text-sm text-muted-foreground">Page {page} of {pageCount}</span>
            <Button variant="outline" className="min-h-11" disabled={page >= pageCount || customers.isFetching}
              onClick={() => setPage((current) => current + 1)}>Next</Button>
          </nav>
        )}
      </div>
    </AppShell>
  );
}
