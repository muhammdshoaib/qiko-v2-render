"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, Network } from "lucide-react";
import { Logo, cn } from "@qiko/ui";
import { DemoPath } from "@/components/crm/demo-path";
import { HonestyBadge } from "./honesty-badge";
import { TABS, type CockpitTab } from "./model";

export function IntelligenceCockpitShell({
  tab,
  onTabChange,
  children,
}: {
  tab: CockpitTab;
  onTabChange: (tab: CockpitTab) => void;
  children: React.ReactNode;
}) {
  const router = useRouter();

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-[#05070d] text-slate-200">
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-white/[0.06] px-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={() => router.push("/studio")}
            className="flex shrink-0 items-center gap-1.5 rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
          >
            <ArrowLeft className="size-4" />
            <span className="hidden sm:inline">Studio</span>
          </button>
          <span className="hidden h-4 w-px bg-white/10 sm:block" />
          <Logo iconOnly className="hidden size-7 sm:block" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">Qiko Creator</p>
            <p className="flex items-center gap-1.5 text-[10px] text-slate-500">
              <Network className="size-3" />
              Intelligence layer · Qiko
              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-px text-amber-300">DEV</span>
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden items-center gap-1.5 text-[11px] text-slate-400 sm:flex">
            <span className="size-1.5 rounded-full bg-cyan-300" /> 1 worker · prototype
          </span>
          <HonestyBadge kind="illustrative" />
        </div>
      </header>

      <nav aria-label="Control room" className="flex shrink-0 gap-1 overflow-x-auto border-b border-white/[0.06] px-3">
        {TABS.map((item) => {
          const active = item.id === tab;
          return (
            <button
              key={item.id}
              type="button"
              aria-current={active ? "page" : undefined}
              onClick={() => onTabChange(item.id)}
              className={cn(
                "shrink-0 border-b-2 px-3 py-2.5 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                active ? "border-indigo-400 text-white" : "border-transparent text-slate-400 hover:text-white",
              )}
            >
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="shrink-0 border-b border-white/[0.06] px-3 py-2 sm:px-4">
        <DemoPath compact />
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
