"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronLeft, LayoutDashboard, LogOut, Menu, Settings, Sparkles, Users, CreditCard, Wrench, X } from "lucide-react";
import { Logo, cn } from "@qiko/ui";
import { logout } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/workers", label: "Workers", icon: Users },
  { href: "/billing", label: "Pricing", icon: CreditCard },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const inStudio = pathname.startsWith("/studio");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <div className="flex min-h-screen bg-[#050810]">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-white/10 bg-[#040b1c] shadow-[0_0_40px_rgba(3,8,20,0.8)]",
          "transform transition-transform duration-300 ease-in-out max-md:-translate-x-full",
          mobileOpen && "max-md:translate-x-0",
        )}
        style={{ width: collapsed ? 72 : 200 }}
      >
        <div className="relative flex h-16 items-center justify-center border-b border-white/5 px-4">
          <div className="flex items-center justify-center overflow-hidden">
            <Logo iconOnly={collapsed} />
          </div>
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="absolute -right-3 top-1/2 mr-5 hidden size-7 -translate-y-1/2 items-center justify-center rounded-full border border-white/10 bg-[#111827] text-slate-300 shadow-md transition-all hover:bg-[#1f2937] hover:text-white md:flex"
          >
            <ChevronLeft className={cn("size-4 transition-transform", collapsed && "rotate-180")} />
          </button>
        </div>
        <div className="border-b border-white/10 px-3 py-3">
          <button
            onClick={() => router.push(inStudio ? "/dashboard" : "/studio")}
            className="flex w-full items-center gap-2 rounded-xl bg-white/[0.02] px-3 py-2.5 text-xs font-medium transition-all hover:bg-white/[0.05]"
          >
            {inStudio ? <Sparkles className="size-4 shrink-0 text-[#A78BFA]" /> : <Wrench className="size-4 shrink-0 text-[#22D3EE]" />}
            {!collapsed && (
              <span className="text-slate-300">
                {inStudio ? "Studio" : "Creator"} <span className="text-slate-500">- {inStudio ? "Creator" : "Studio"}</span>
              </span>
            )}
          </button>
        </div>
        <nav className="flex-1 px-3 py-3">
          <ul className="flex flex-col gap-1">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname.startsWith(href + "/");
              return (
                <li key={href}>
                  <Link
                    href={href}
                    className={cn(
                      "group relative flex w-full items-center gap-3 rounded-xl px-3 py-3 transition-all duration-200",
                      active
                        ? "border border-white/10 bg-gradient-to-br from-[#6366F1]/20 to-[#22D3EE]/20 text-white"
                        : "border border-transparent text-slate-400 hover:bg-white/5 hover:text-white",
                    )}
                  >
                    {active && (
                      <span
                        className="absolute left-0 top-1/2 h-8 w-1 -translate-y-1/2 rounded-r-full"
                        style={{ background: "linear-gradient(#6366F1, #22D3EE)" }}
                      />
                    )}
                    <Icon className={cn("size-5 shrink-0", active && "text-[#22D3EE]")} />
                    {!collapsed && <span className="text-sm font-medium whitespace-nowrap">{label}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="sticky bottom-0 border-t border-white/10 bg-[#040b1c] p-3">
          <button
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-slate-400 transition-all hover:bg-white/5 hover:text-white"
          >
            <LogOut className="size-5 shrink-0" />
            {!collapsed && <span className="text-sm font-medium">Logout</span>}
          </button>
        </div>
        <button onClick={() => setMobileOpen(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white md:hidden">
          <X className="size-5" />
        </button>
      </aside>

      <div className="flex flex-1 flex-col transition-[margin-left] duration-300 ease-in-out" style={{ marginLeft: 0 }}>
        <div className="sticky top-0 z-30 border-b border-white/5 bg-[#050810]/95 backdrop-blur md:hidden">
          <div className="flex items-center justify-between p-4">
            <button onClick={() => setMobileOpen(true)} className="-ml-2 p-2 text-slate-400 hover:text-white">
              <Menu className="size-5" />
            </button>
            <span className="text-lg font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>{title}</span>
            <div className="w-9" />
          </div>
        </div>
        <main className="flex-1 md:ml-[200px]">{children}</main>
      </div>
    </div>
  );
}
