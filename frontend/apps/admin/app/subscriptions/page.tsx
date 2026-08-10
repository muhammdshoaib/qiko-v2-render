"use client";

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Badge, SegmentedFilter, type Column } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { formatMoney, listCustomers, type Customer } from "@/lib/api";

// The plan the directory reports is already derived from the ACTIVE subscription (a lapsed one reads as
// "free"), so it is the subscription state rather than a guess at it. Which is also why this page can be
// the customer directory narrowed by plan, instead of a second source of truth about billing.
const PLANS = [
  { value: "", label: "All plans" },
  { value: "free", label: "Free" },
  { value: "starter", label: "Starter" },
  { value: "pro", label: "Pro" },
] as const;

const columns: Column<Customer>[] = [
  {
    id: "email", header: "Account", rowHeader: true, sortable: true,
    cell: (row) => (
      <div className="min-w-0">
        <p className="truncate font-medium">{row.email}</p>
        <p className="truncate text-xs text-muted-foreground">{row.user_id}</p>
      </div>
    ),
  },
  {
    id: "plan", header: "Plan", sortable: true,
    cell: (row) => (
      <Badge variant={row.plan === "free" ? "muted" : "default"}>{row.plan}</Badge>
    ),
  },
  { id: "earnings", header: "Billed to date", sortable: true, numeric: true,
    cell: (row) => formatMoney(row.earnings_cents) },
];

function SubscriptionsView() {
  const router = useRouter();
  const params = useSearchParams();
  const plan = params.get("plan") ?? "";

  const setFilter = useCallback((value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set("plan", value); else next.delete("plan");
    next.delete("page");
    router.replace(`?${next.toString()}`, { scroll: false });
  }, [params, router]);

  return (
    <DirectoryPage<Customer>
      title="Subscriptions"
      noun="accounts"
      searchLabel="Search subscriptions by customer email"
      searchPlaceholder="Search by customer email"
      queryKey="subscriptions"
      filterToken={plan}
      onClearFilters={() => router.replace("?", { scroll: false })}
      // Highest billed first, matching what the endpoint returns unsorted, so the header shows an active
      // sort instead of an order the operator cannot account for.
      defaultSort={{ sort: "earnings", order: "desc" }}
      // The plan filter has existed on this endpoint all along and this page never sent it, so the only
      // way to answer "who is still on free" was to page through everything.
      fetchPage={(search, page, sort) => listCustomers(search, page, sort, plan || undefined)}
      rowKey={(row) => row.user_id}
      columns={columns}
      filters={
        <SegmentedFilter label="Filter by plan" value={plan}
          options={PLANS.map((p) => ({ value: p.value, label: p.label }))}
          onChange={setFilter} />
      }
      emptyMessage={(filtered) => filtered
        ? "No accounts match this search or plan."
        : "No accounts yet."}
    />
  );
}

export default function SubscriptionsPage() {
  return <Suspense fallback={null}><SubscriptionsView /></Suspense>;
}
