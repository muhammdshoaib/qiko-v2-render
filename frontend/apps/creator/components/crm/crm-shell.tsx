"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { Button, cn } from "@qiko/ui";
import { useCrm } from "@/lib/crm/store";
import { DemoPath } from "./demo-path";
import { PrototypeBadge } from "./prototype-badge";

const LINKS = [
  { href: "/crm", label: "Overview" },
  { href: "/crm/pipeline", label: "Pipeline" },
  { href: "/crm/invoices", label: "Invoices" },
  { href: "/crm/tasks", label: "Tasks" },
  { href: "/crm/channels", label: "Channels" },
];

export function CrmShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const crm = useCrm();

  return (
    <AppShell title="CRM">
      <div className="border-b border-white/[0.06] px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-7xl flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
                  Qiko CRM
                </h1>
                <PrototypeBadge />
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Internal commercial records. CRM Agent playbooks are a labelled prototype — not live automation.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={crm.reset}>
              Reset sample data
            </Button>
          </div>
          <nav aria-label="CRM" className="flex gap-1 overflow-x-auto">
            {LINKS.map((link) => {
              const active = link.href === "/crm" ? pathname === "/crm" : pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "rounded-lg px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                    active ? "bg-white/[0.06] text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white",
                  )}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <div className="mb-6">
          <DemoPath />
        </div>
        {!crm.ready ? (
          <div className="space-y-3" aria-busy="true" aria-label="Loading CRM">
            <div className="h-24 animate-pulse rounded-2xl bg-muted" />
            <div className="h-64 animate-pulse rounded-2xl bg-muted" />
          </div>
        ) : children}
      </div>
    </AppShell>
  );
}
