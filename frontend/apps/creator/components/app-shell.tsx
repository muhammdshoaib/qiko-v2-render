"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  ChevronLeft,
  Link2,
  LogOut,
  Menu,
  Settings,
  Users,
  X,
} from "lucide-react";
import { Logo, cn } from "@qiko/ui";
import { logout } from "@/lib/api";
import { DemoGuide } from "@/components/studio/demo-guide";

type NavItem = {
  id: string;
  label: string;
  icon: typeof Activity;
  href: string;
  badge?: string;
  count?: string;
  live?: boolean;
};

/** Pulse sidebar: only surfaces called out in the Pulse functionality summary / sprint nav. */
const COMPANY_BRAIN: NavItem[] = [
  { id: "pulse", label: "Pulse", icon: Activity, href: "/dashboard", live: true },
  { id: "workers", label: "Knowledge", icon: Users, href: "/workers", count: "7" },
];

const SETUP: NavItem[] = [
  { id: "connections", label: "Connections", icon: Link2, href: "/studio/intelligence?tab=connections", count: "15" },
  { id: "settings", label: "Settings", icon: Settings, href: "/settings" },
];

function isActive(pathname: string, search: string, item: NavItem) {
  if (item.id === "pulse") {
    return pathname === "/dashboard";
  }
  if (item.id === "workers") {
    return pathname === "/workers" || pathname.startsWith("/workers/") || pathname.startsWith("/knowledge");
  }
  if (item.id === "connections") {
    return pathname.startsWith("/studio/intelligence") && search.includes("tab=connections");
  }
  if (item.id === "settings") {
    return pathname === "/settings" || pathname.startsWith("/settings/");
  }
  return pathname === item.href || pathname.startsWith(item.href + "/");
}

function NavButton({
  item,
  collapsed,
  active,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
  onNavigate: () => void;
}) {
  const Icon = item.icon;
  const className = cn(
    "group relative flex w-full items-center gap-3 rounded-xl px-2.5 transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
    active
      ? "h-9 bg-indigo-50 font-semibold text-indigo-700"
      : "h-9 text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  );

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      className={className}
      title={collapsed ? item.label : undefined}
    >
      {active && (
        <span className="absolute -left-2.5 top-1/2 h-[22px] w-[3px] -translate-y-1/2 rounded-r bg-indigo-500" />
      )}
      <Icon className={cn("size-[17px] shrink-0", active ? "text-indigo-600" : "text-slate-400")} />
      {!collapsed && (
        <>
          <span className="truncate text-[14px] font-medium whitespace-nowrap">{item.label}</span>
          {item.live && (
            <span
              className="ml-auto size-[7px] shrink-0 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.15)]"
              aria-label="Live"
            />
          )}
          {item.badge && !item.live && (
            <span className="ml-auto rounded-full bg-indigo-600 px-1.5 font-mono text-[10px] leading-[17px] text-white">
              {item.badge}
            </span>
          )}
          {item.count && !item.badge && !item.live && (
            <span className="ml-auto font-mono text-[10px] text-slate-400">{item.count}</span>
          )}
        </>
      )}
    </Link>
  );
}

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Suspense
      fallback={(
        <AppShellFrame title={title} search="">
          {children}
        </AppShellFrame>
      )}
    >
      <AppShellWithSearch title={title}>{children}</AppShellWithSearch>
    </Suspense>
  );
}

function AppShellWithSearch({ title, children }: { title: string; children: React.ReactNode }) {
  const searchParams = useSearchParams();
  const search = searchParams?.toString() ? `?${searchParams.toString()}` : "";
  return <AppShellFrame title={title} search={search}>{children}</AppShellFrame>;
}

function AppShellFrame({ title, children, search }: { title: string; children: React.ReactNode; search: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const inStudio = pathname.startsWith("/studio");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobileMenu = () => setMobileOpen(false);

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <div className="flex min-h-screen min-w-0 overflow-x-hidden bg-slate-50">
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-40 bg-slate-900/30 lg:hidden"
          onClick={closeMobileMenu}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-slate-200 bg-white shadow-sm",
          "transform transition-transform duration-300 ease-in-out -translate-x-full lg:translate-x-0",
          mobileOpen && "translate-x-0",
        )}
        style={{ width: collapsed ? 72 : 220 }}
        aria-label="Main"
      >
        <div className="relative flex items-center gap-2.5 border-b border-slate-200 px-3 py-3.5">
          <div className="flex min-w-0 items-center gap-2 overflow-hidden">
            <Logo iconOnly={collapsed} />
            {!collapsed && (
              <span className="truncate text-[16px] font-semibold tracking-[-0.01em] text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
                Pulse
              </span>
            )}
          </div>
          <button
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="absolute -right-3 top-1/2 hidden size-7 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 lg:flex"
          >
            <ChevronLeft className={cn("size-4 transition-transform", collapsed && "rotate-180")} />
          </button>
        </div>

        <div className="flex items-center gap-2.5 border-b border-slate-200 px-3 py-3">
          <span className="grid size-[30px] shrink-0 place-items-center rounded-lg bg-indigo-600 text-[12px] font-extrabold text-white" style={{ fontFamily: "var(--font-display)" }}>
            JM
          </span>
          {!collapsed && (
            <span className="min-w-0">
              <b className="block truncate text-[13px] font-semibold text-slate-900">Joseph Mews</b>
              <span className="block truncate text-[11.5px] text-slate-500">josephmews.co.uk</span>
            </span>
          )}
        </div>

        <nav aria-label="Company brain" className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2.5 py-2">
          {!collapsed && (
            <div className="px-2.5 pb-1.5 pt-2 font-mono text-[10px] tracking-[0.12em] text-slate-400 uppercase">
              Company brain
            </div>
          )}
          <ul className="flex flex-col gap-0.5">
            {COMPANY_BRAIN.map((item) => (
              <li key={item.id}>
                <NavButton
                  item={item}
                  collapsed={collapsed}
                  active={isActive(pathname, search, item)}
                  onNavigate={closeMobileMenu}
                />
              </li>
            ))}
          </ul>

          {!collapsed && (
            <div className="mt-2 border-t border-slate-100 px-2.5 pb-1.5 pt-4 font-mono text-[10px] tracking-[0.12em] text-slate-400 uppercase">
              Setup
            </div>
          )}
          {collapsed && <div className="my-2 border-t border-slate-100" />}
          <ul className="flex flex-col gap-0.5">
            {SETUP.map((item) => (
              <li key={item.id}>
                <NavButton
                  item={item}
                  collapsed={collapsed}
                  active={isActive(pathname, search, item)}
                  onNavigate={closeMobileMenu}
                />
              </li>
            ))}
          </ul>
        </nav>

        <div className="mt-auto space-y-2 border-t border-slate-200 p-3">
          {!collapsed && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-center justify-between text-[12.5px]">
                <b className="font-semibold text-slate-900">Worker capacity</b>
                <span className="font-mono text-[11px] text-slate-500">2 / 2</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                <i className="block h-full w-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" />
              </div>
              <p className="mt-1.5 text-[11.5px] text-slate-500">0 more workers on your plan</p>
            </div>
          )}
          <button
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-xl px-2.5 py-2.5 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            <LogOut className="size-5 shrink-0" />
            {!collapsed && <span className="text-sm font-medium">Logout</span>}
          </button>
        </div>

        <button
          onClick={closeMobileMenu}
          aria-label="Close menu"
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 lg:hidden"
        >
          <X className="size-5" />
        </button>
      </aside>

      <main
        className={cn(
          "flex min-h-screen min-w-0 flex-1 flex-col overflow-x-hidden transition-[margin-left] duration-300 ease-in-out",
          collapsed ? "lg:ml-[72px]" : "lg:ml-[220px]",
        )}
      >
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur lg:hidden">
          <div className="flex items-center justify-between p-4">
            <button
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
              className="-ml-2 p-2 text-slate-500 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
            >
              <Menu className="size-5" />
            </button>
            <span className="text-lg font-bold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
              {title}
            </span>
            <div className="w-9" />
          </div>
        </header>
        {inStudio && <DemoGuide />}
        <div className="min-w-0 flex-1 overflow-x-hidden bg-slate-50">{children}</div>
      </main>
    </div>
  );
}
