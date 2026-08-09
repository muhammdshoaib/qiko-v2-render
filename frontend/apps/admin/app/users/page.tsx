"use client";

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Badge, SegmentedFilter, type Column } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { listUsers, type UserRow } from "@/lib/api";

const columns: Column<UserRow>[] = [
  {
    id: "name", header: "User", rowHeader: true, sortable: true,
    cell: (row) => (
      <div className="min-w-0">
        <p className="truncate font-medium">{row.name || row.email}</p>
        {row.name && <p className="truncate text-xs text-muted-foreground">{row.email}</p>}
      </div>
    ),
  },
  { id: "tenant", header: "Tenant", sortable: true, hideBelow: "md",
    cell: (row) => row.tenant_id ?? <span className="text-muted-foreground">No tenant</span> },
  {
    id: "role", header: "Role", sortable: true,
    cell: (row) => (
      <span className="flex flex-wrap items-center gap-1">
        <Badge variant="muted">{row.role_label}</Badge>
        {/* Platform access is a separate system from the tenant role, so it is labelled as such. The
            scope is only returned to a manage_admins caller, so fall back to the plain membership
            badge rather than rendering nothing. */}
        {row.platform_role
          ? <Badge>Platform {row.platform_role.replace("_", " ")}</Badge>
          : row.is_platform_admin && <Badge>Platform admin</Badge>}
      </span>
    ),
  },
  {
    id: "twofa", header: "2FA", sortable: true,
    // Sorting by this is how an operator finds the accounts to chase, which is why the server allows
    // it and why the column exists at all.
    cell: (row) => (
      <span className={row.twofa_enabled ? "text-muted-foreground" : "text-destructive"}>
        {row.twofa_enabled ? "On" : "Off"}
      </span>
    ),
  },
];

const ROLES = [
  { value: "", label: "Any role" },
  { value: "owner", label: "Owner" },
  { value: "admin", label: "Admin" },
  { value: "editor", label: "Editor" },
  { value: "viewer", label: "Viewer" },
] as const;

function UsersView() {
  const router = useRouter();
  const params = useSearchParams();
  const role = params.get("role") ?? "";
  const twofa = params.get("twofa") ?? "";

  const setFilter = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    next.delete("page");
    router.replace(`?${next.toString()}`, { scroll: false });
  }, [params, router]);

  return (
    <DirectoryPage<UserRow>
      title="Users"
      noun="users"
      searchLabel="Search users by email or name"
      searchPlaceholder="Search by email or name..."
      queryKey="admin-users"
      filterToken={`${role}|${twofa}`}
      onClearFilters={() => router.replace("?", { scroll: false })}
      // Both filters have existed on the server since leg B and were unreachable. "Who has not turned
      // 2FA on" is the question an operator actually asks of a user directory.
      fetchPage={(search, page, sort) =>
        listUsers(search, page, undefined, sort, { role, twofa })}
      rowKey={(row) => row.id}
      columns={columns}
      filters={
        <div className="flex flex-wrap items-end gap-4">
          <SegmentedFilter label="Filter by role" value={role}
            options={ROLES.map((r) => ({ value: r.value, label: r.label }))}
            onChange={(value) => setFilter("role", value)} />
          <SegmentedFilter label="Filter by two-factor state" value={twofa}
            options={[{ value: "", label: "Any 2FA" }, { value: "false", label: "2FA off" },
                      { value: "true", label: "2FA on" }]}
            onChange={(value) => setFilter("twofa", value)} />
        </div>
      }
      emptyMessage={(filtered) => filtered ? "No users match this search or filter." : "No users yet."}
    />
  );
}

export default function UsersPage() {
  return <Suspense fallback={null}><UsersView /></Suspense>;
}
