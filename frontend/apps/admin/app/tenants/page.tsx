"use client";

import { useState } from "react";
import { Badge, Button, type Column } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { RowActivityDialog } from "@/components/row-activity-dialog";
import { formatMoney, listTenants, type TenantRow } from "@/lib/api";

// Sortable keys mirror CUSTOMER_SORTS/TENANT_SORTS in app/modules/admin/sorting.py. A column marked
// sortable here that the server does not allow would return a 422, so the two lists have to agree.
const columns: Column<TenantRow>[] = [
  {
    id: "email", header: "Tenant", rowHeader: true, sortable: true,
    cell: (row) => (
      <div className="min-w-0">
        <p className="truncate font-medium">{row.email}</p>
        <p className="truncate text-xs text-muted-foreground">{row.tenant_id}</p>
      </div>
    ),
  },
  {
    id: "plan", header: "Plan", sortable: true,
    cell: (row) => (
      <span className="flex flex-wrap items-center gap-1">
        <Badge variant="muted">{row.plan}</Badge>
        {row.is_studio && <Badge>Studio</Badge>}
      </span>
    ),
  },
  { id: "users", header: "Users", sortable: true, numeric: true, hideBelow: "lg",
    cell: (row) => row.user_count },
  { id: "workers", header: "Workers", sortable: true, numeric: true, hideBelow: "lg",
    cell: (row) => row.worker_count },
  { id: "earnings", header: "Earnings", sortable: true, numeric: true,
    cell: (row) => formatMoney(row.earnings_cents) },
];

export default function TenantsPage() {
  const [active, setActive] = useState<TenantRow | null>(null);
  return (
    <>
    <DirectoryPage<TenantRow>
      title="Tenants"
      noun="tenants"
      searchLabel="Search tenants by email or id"
      searchPlaceholder="Search by email..."
      queryKey="admin-tenants"
      // The endpoint returns highest-earning first when no sort is requested, so the header reflects
      // that rather than showing an unsorted table the operator cannot explain.
      defaultSort={{ sort: "earnings", order: "desc" }}
      fetchPage={(search, page, sort) => listTenants(search, page, sort)}
      rowKey={(row) => row.tenant_id}
      columns={columns}
      actions={(row) => (
        <Button variant="outline" className="min-h-11" onClick={() => setActive(row)}
          aria-label={`Recent activity for ${row.email}`}>
          Activity
        </Button>
      )}
      emptyMessage={(filtered) => filtered ? "No tenants match this search." : "No tenants yet."}
    />
    <RowActivityDialog
      open={Boolean(active)}
      title={active?.email ?? ""}
      subtitle={active?.tenant_id}
      tenantId={active?.tenant_id}
      onClose={() => setActive(null)}
    />
    </>
  );
}
