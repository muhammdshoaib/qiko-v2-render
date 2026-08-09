"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge, Button, type Column } from "@qiko/ui";
import { CustomerDetailDialog } from "@/components/customer-detail-dialog";
import { DirectoryPage } from "@/components/directory-page";
import { adminMe, formatMoney, listCustomers, type Customer } from "@/lib/api";

export default function CustomersPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });

  // Note the absent columns: /admin/customers deliberately returns no user or worker counts, and the
  // server refuses to sort by them for the same reason, since ordering by a field the response omits
  // discloses that field's ordering without ever showing it. Those live on /tenants.
  const columns: Column<Customer>[] = [
    {
      id: "email", header: "Customer", rowHeader: true, sortable: true,
      cell: (row) => <span className="truncate font-medium">{row.email}</span>,
    },
    { id: "plan", header: "Plan", sortable: true,
      cell: (row) => <Badge variant="muted">{row.plan}</Badge> },
    { id: "earnings", header: "Earnings", sortable: true, numeric: true,
      cell: (row) => formatMoney(row.earnings_cents) },
  ];

  return (
    <>
      <DirectoryPage<Customer>
        title="Customers"
        noun="customers"
        searchLabel="Search customers by email"
        searchPlaceholder="Search by email..."
        queryKey="customers"
        defaultSort={{ sort: "earnings", order: "desc" }}
        fetchPage={(search, page, sort) => listCustomers(search, page, sort)}
        rowKey={(row) => row.user_id}
        columns={columns}
        actions={(row) => (
          <Button variant="outline" className="min-h-11"
            onClick={(event) => { opener.current = event.currentTarget; setSelected(row.user_id); }}
            aria-label={`View details for ${row.email}`}>
            Details
          </Button>
        )}
        emptyMessage={(filtered) =>
          filtered ? "No customers match this search." : "No customers yet."}
      />
      {me.data && (
        <CustomerDetailDialog
          customerId={selected}
          capabilities={me.data.capabilities}
          opener={opener.current}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
