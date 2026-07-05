"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, Users, BarChart3, Receipt, ShieldCheck, LogOut } from "lucide-react";
import { Button, Logo, cn } from "@qiko/ui";
import { logout } from "@/lib/api";

const NAV = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/invoices", label: "Invoices", icon: Receipt },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/security", label: "Security", icon: ShieldCheck },
];

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <div className="grid min-h-screen grid-cols-[15rem_1fr] max-md:grid-cols-1">
      <aside className="flex flex-col gap-1 border-r border-sidebar-border bg-sidebar px-3 py-4 max-md:hidden">
        <div className="flex items-center gap-2 px-2 pb-4">
          <Logo />
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">ADMIN</span>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link key={href} href={href}
                className={cn("flex items-center gap-2 rounded-md p-2 text-sm transition-colors",
                  active ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground")}>
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto">
          <Button variant="ghost" className="w-full justify-start text-sidebar-foreground/70" onClick={onLogout}>
            <LogOut className="size-4" /> Sign out
          </Button>
        </div>
      </aside>
      <div className="flex flex-col">
        <header className="flex h-14 items-center border-b border-sidebar-border px-6">
          <h1 className="text-sm font-semibold">{title}</h1>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
