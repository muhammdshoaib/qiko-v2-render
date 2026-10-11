"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Briefcase, ChevronLeft, LayoutDashboard, Lock, LogOut, Menu, Settings, Sparkles, Users, CreditCard, Wrench, X } from "lucide-react";
import { Logo, cn } from "@qiko/ui";
import { logout } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/crm", label: "CRM", icon: Briefcase },
  { href: "/workers", label: "Workers", icon: Users },
  { href: "/billing", label: "Pricing", icon: CreditCard, locked: true },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
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
    <div className="flex min-h-screen min-w-0 overflow-x-hidden bg-[#05070d]">
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={closeMobileMenu}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-white/[0.06] bg-[#070a12] shadow-[0_0_40px_rgba(3,8,20,0.8)]",
          "transform transition-transform duration-300 ease-in-out -translate-x-full lg:translate-x-0",
          mobileOpen && "translate-x-0",
        )}
        style={{ width: collapsed ? 72 : 200 }}
      >
        <div className="relative flex h-16 items-center justify-center border-b border-white/[0.06] px-4">
          <div className="flex items-center justify-center overflow-hidden">
            <Logo iconOnly={collapsed} />
          </div>
          <button
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="absolute -right-3 top-1/2 mr-5 hidden size-7 -translate-y-1/2 items-center justify-center rounded-full border border-white/10 bg-[#111827] text-slate-300 shadow-md transition-all hover:bg-[#1f2937] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 lg:flex"
          >
            <ChevronLeft className={cn("size-4 transition-transform", collapsed && "rotate-180")} />
          </button>
        </div>
        <div className="border-b border-white/[0.06] px-3 py-3">
          <button
            onClick={() => {
              closeMobileMenu();
              router.push(inStudio ? "/dashboard" : "/studio");
            }}
            className="flex w-full items-center gap-2 rounded-xl border border-white/[0.06] bg-white/[0.015] px-3 py-2.5 text-xs font-medium transition-colors hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
          >
            {inStudio ? <Sparkles className="size-4 shrink-0 text-violet-400" /> : <Wrench className="size-4 shrink-0 text-cyan-400" />}
            {!collapsed && (
              <span className="text-slate-300">
                {inStudio ? "Studio" : "Creator"} <span className="text-slate-500">- {inStudio ? "Creator" : "Studio"}</span>
              </span>
            )}
          </button>
        </div>
        <nav aria-label="Primary" className="flex-1 px-3 py-3">
          <ul className="flex flex-col gap-1">
            {NAV.map(({ href, label, icon: Icon, locked }) => {
              if (locked) {
                return (
                  <li key={href}>
                    <div
                      aria-disabled="true"
                      title="Locked"
                      className="group relative flex w-full cursor-not-allowed items-center gap-3 rounded-xl border border-transparent px-3 py-3 text-slate-500 opacity-60"
                    >
                      <Icon className="size-5 shrink-0 text-slate-600" />
                      {!collapsed && (
                        <>
                          <span className="text-sm font-medium whitespace-nowrap">{label}</span>
                          <Lock className="ml-auto size-4 shrink-0 text-slate-500" />
                        </>
                      )}
                    </div>
                  </li>
                );
              }
              const active = pathname === href || pathname.startsWith(href + "/");
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    onClick={closeMobileMenu}
                    className={cn(
                      "group relative flex w-full items-center gap-3 rounded-xl px-3 py-3 transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500",
                      active
                        ? "border border-cyan-500/30 bg-cyan-500/10 text-white"
                        : "border border-transparent text-slate-400 hover:bg-white/[0.04] hover:text-white",
                    )}
                  >
                    {active && (
                      <span className="absolute left-0 top-1/2 h-8 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-cyan-400 to-violet-500" />
                    )}
                    <Icon className={cn("size-5 shrink-0", active ? "text-cyan-400" : "text-slate-500")} />
                    {!collapsed && <span className="text-sm font-medium whitespace-nowrap">{label}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="sticky bottom-0 border-t border-white/[0.06] bg-[#070a12] p-3">
          <button
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
          >
            <LogOut className="size-5 shrink-0" />
            {!collapsed && <span className="text-sm font-medium">Logout</span>}
          </button>
        </div>
        <button onClick={closeMobileMenu} aria-label="Close menu" className="absolute top-4 right-4 text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 lg:hidden">
          <X className="size-5" />
        </button>
      </aside>

      <main
        className={cn(
          "flex min-h-screen min-w-0 flex-1 flex-col overflow-x-hidden transition-[margin-left] duration-300 ease-in-out",
          collapsed ? "lg:ml-[72px]" : "lg:ml-[200px]",
        )}
      >
        <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[#05070d]/95 backdrop-blur lg:hidden">
          <div className="flex items-center justify-between p-4">
            <button onClick={() => setMobileOpen(true)} aria-label="Open menu" className="-ml-2 p-2 text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500">
              <Menu className="size-5" />
            </button>
            <span className="text-lg font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>{title}</span>
            <div className="w-9" />
          </div>
        </header>
        <div className="min-w-0 flex-1 overflow-x-hidden">{children}</div>
      </main>
    </div>
  );
}
