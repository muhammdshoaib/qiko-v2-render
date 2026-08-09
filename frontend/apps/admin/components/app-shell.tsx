"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, Users, BarChart3, Receipt, ShieldCheck, ShieldAlert, LogOut, Menu, X, UserCog, CreditCard, Building2, UsersRound, Bot, Activity, Coins, Server, ScrollText } from "lucide-react";
import { Button, Logo, cn } from "@qiko/ui";
import { adminMe, ApiError, logout, type Capability } from "@/lib/api";

// `requires` gates the entry on a capability. Entries without it stay visible to every platform
// admin, so nothing that worked before disappears. Hiding a denied entry is nicer than letting the
// admin click into a 403, but it is presentation only: the server enforces every one of these.
// Every destination declares the capability its BACKEND actually enforces. Four entries used to
// declare none while their endpoints required one, so a narrowed admin saw the nav item, clicked it,
// and got an error card. A menu that offers what it cannot deliver is worse than a shorter menu.
const NAV: { href: string; label: string; icon: typeof Users; requires?: Capability }[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard, requires: "view_customers" },
  { href: "/customers", label: "Customers", icon: Users, requires: "view_customers" },
  { href: "/tenants", label: "Tenants", icon: Building2, requires: "view_customers" },
  { href: "/users", label: "Users", icon: UsersRound, requires: "view_customers" },
  { href: "/workers", label: "Workers", icon: Bot, requires: "view_customers" },
  { href: "/monitoring", label: "Monitoring", icon: Activity, requires: "view_customers" },
  { href: "/ai-cost", label: "AI Cost", icon: Coins, requires: "view_ai_cost" },
  { href: "/system", label: "System", icon: Server, requires: "view_system_stats" },
  { href: "/subscriptions", label: "Subscriptions", icon: CreditCard, requires: "view_customers" },
  { href: "/invoices", label: "Invoices", icon: Receipt, requires: "manage_billing" },
  { href: "/admins", label: "Platform Admins", icon: UserCog, requires: "manage_admins" },
  // view_audit, not view_customers: the trail carries authentication events, so a reader learns which
  // accounts exist and when each colleague works. It is deliberately outside the viewer default set.
  { href: "/audit", label: "Audit Log", icon: ScrollText, requires: "view_audit" },
  { href: "/analytics", label: "Analytics", icon: BarChart3, requires: "view_customers" },
  { href: "/security", label: "Security", icon: ShieldCheck },
];

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  // Detect the "logged in but no 2FA" state: the platform-admin gate returns 403 "platform admin MFA
  // required" until the admin enrols 2FA. Instead of every page showing a generic "unavailable" error,
  // send the admin straight into 2FA onboarding on /security. Deduped with pages' own ["admin-me"]
  // queries; retry:false so a real 403 resolves immediately.
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe, retry: false });
  const mfaRequired =
    me.error instanceof ApiError && me.error.status === 403 && /mfa/i.test(me.error.message);
  const needsOnboarding = mfaRequired && !pathname.startsWith("/security");
  // A MISSING capabilities field means "unknown", not "none": treating it as an empty list hid
  // Customers and Invoices from every admin whenever /admin/me came from an older backend, a cached
  // response or a mock. Only filter once the field is actually present.
  const capabilities = me.data?.capabilities;
  const visibleNav = capabilities
    ? NAV.filter((entry) => !entry.requires || capabilities.includes(entry.requires))
    : NAV;
  useEffect(() => {
    if (needsOnboarding) router.replace("/security");
  }, [needsOnboarding, router]);
  const mobileDialog = useRef<HTMLDialogElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (mobileOpen) mobileDialog.current?.showModal();
    else if (mobileDialog.current?.open) mobileDialog.current.close();
  }, [mobileOpen]);

  async function onLogout() {
    try {
      await logout();
    } finally {
      queryClient.clear();
      window.location.assign("/login");
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
          {visibleNav.map(({ href, label, icon: Icon }) => {
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
      <dialog
        ref={mobileDialog}
        aria-labelledby="mobile-nav-title"
        onClose={() => { setMobileOpen(false); requestAnimationFrame(() => menuButton.current?.focus()); }}
        className="m-0 h-dvh w-72 max-w-[85vw] border-0 bg-sidebar p-4 text-sidebar-foreground shadow-2xl backdrop:bg-black/60 md:hidden"
      >
        <div className="flex h-full flex-col">
          <div className="mb-4 flex items-center justify-between"><div><Logo /><span id="mobile-nav-title" className="sr-only">Admin navigation</span></div><Button variant="ghost" size="icon" autoFocus onClick={() => mobileDialog.current?.close()} aria-label="Close menu"><X className="size-5" /></Button></div>
          <nav className="flex flex-col gap-1" aria-label="Admin mobile navigation">
            {visibleNav.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} onClick={() => mobileDialog.current?.close()} className={cn("flex min-h-11 items-center gap-2 rounded-md p-2 text-sm", pathname.startsWith(href) ? "bg-sidebar-accent font-medium" : "text-sidebar-foreground/70")}><Icon className="size-4" />{label}</Link>
            ))}
          </nav>
          <Button variant="ghost" className="mt-auto min-h-11 justify-start" onClick={onLogout}><LogOut className="size-4" /> Sign out</Button>
        </div>
      </dialog>
      <div className="flex flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-sidebar-border px-4 sm:px-6">
          <button ref={menuButton} type="button" className="inline-flex size-10 items-center justify-center rounded-md hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu className="size-5" /></button>
          <h1 className="text-sm font-semibold">{title}</h1>
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          {needsOnboarding ? (
            <div role="status" className="mx-auto flex max-w-md items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
              <ShieldAlert className="mt-0.5 size-5 shrink-0" />
              <div>
                <p className="font-medium">Two-factor authentication is required to use the admin.</p>
                <p className="mt-0.5 text-amber-200/80">
                  Taking you to set it up. If nothing happens, open{" "}
                  <Link href="/security" className="font-medium underline">Security</Link>.
                </p>
              </div>
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
