"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutGrid, MessageSquare, Users, CreditCard, Settings, LogOut, Sparkles } from "lucide-react";
import { Button, Logo, cn } from "@qiko/ui";
import { logout } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Workers", icon: LayoutGrid },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/team", label: "Team", icon: Users },
  { href: "/billing", label: "Billing", icon: CreditCard },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const inStudio = pathname.startsWith("/studio");

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <div className="grid min-h-screen grid-cols-[15rem_1fr] max-md:grid-cols-1">
      <aside className="flex flex-col gap-1 border-r border-white/10 bg-[#040b1c] px-3 py-4 shadow-[0_0_40px_rgba(3,8,20,0.8)] max-md:hidden">
        <div className="px-2 pb-4">
          <Logo />
        </div>
        <button
          onClick={() => router.push(inStudio ? "/dashboard" : "/studio")}
          className="mb-3 flex items-center justify-center gap-2 rounded-xl bg-white/[0.02] px-3 py-2.5 text-xs font-medium text-slate-300 transition-all hover:bg-white/[0.05]"
        >
          <Sparkles className="size-3.5" />
          {inStudio ? "Switch to Creator" : "Switch to Studio"}
        </button>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-3 py-2.5 text-sm font-medium transition-all",
                  active
                    ? "border-white/10 bg-gradient-to-br from-primary/20 to-secondary/20 text-white"
                    : "border-transparent text-slate-400 hover:bg-white/5 hover:text-white",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto">
          <Button variant="ghost" className="w-full justify-start text-slate-400 hover:text-white" onClick={onLogout}>
            <LogOut className="size-4" /> Sign out
          </Button>
        </div>
      </aside>

      <div className="flex flex-col">
        <header className="flex h-14 items-center justify-between border-b border-white/10 px-6">
          <h1 className="text-sm font-semibold">{title}</h1>
          <Button variant="ghost" size="sm" className="md:hidden" onClick={onLogout}>
            <LogOut className="size-4" />
          </Button>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
