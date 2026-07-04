"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Badge, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { listCustomers, type Customer } from "@/lib/api";

export default function CustomersPage() {
  const [search, setSearch] = useState("");
  const customers = useQuery({ queryKey: ["customers", search], queryFn: () => listCustomers(search) });

  return (
    <AppShell title="Customers">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Customers</h2>
            <p className="text-sm text-muted-foreground">{customers.data?.total ?? 0} total</p>
          </div>
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" placeholder="Search by email…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>

        {customers.isError && (
          <Card><CardContent className="py-6 text-sm text-destructive">Not authorized (admin role required).</CardContent></Card>
        )}

        <div className="space-y-2">
          {customers.isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
          {customers.data?.items.map((c: Customer) => (
            <Card key={c.user_id}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-medium">{c.email}</p>
                  <Badge variant="muted">{c.plan}</Badge>
                </div>
                <span className="text-sm font-semibold tabular-nums">${(c.earnings_cents / 100).toFixed(2)}</span>
              </CardContent>
            </Card>
          ))}
          {customers.data?.items.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">No customers.</p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
