"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { listCustomers } from "@/lib/api";

export default function SubscriptionsPage() {
  const [search, setSearch] = useState("");
  const customers = useQuery({ queryKey: ["subscription-customers", search], queryFn: () => listCustomers(search) });
  return <AppShell title="Subscriptions"><div className="mx-auto max-w-4xl space-y-5"><h1 className="text-2xl font-bold">Subscriptions</h1><Input aria-label="Search subscriptions" placeholder="Search by customer email" value={search} onChange={(event) => setSearch(event.target.value)} />{customers.isLoading && <Skeleton className="h-20" />}{customers.isError && <p role="alert" className="text-sm text-destructive">Subscriptions unavailable. <button className="underline" onClick={() => customers.refetch()}>Retry</button></p>}{customers.data?.items.map((customer) => <Card key={customer.user_id}><CardContent className="flex items-center justify-between py-4"><span>{customer.email}</span><span className="font-medium">{customer.plan}</span></CardContent></Card>)}{customers.data?.items.length === 0 && <p className="text-sm text-muted-foreground">No subscriptions found.</p>}</div></AppShell>;
}
