"use client";

import { AppShell } from "@/components/app-shell";
import { cn } from "@qiko/ui";
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
  return (
    <AppShell title="Intelligence">
      <div className="flex min-h-[calc(100dvh-3.5rem)] flex-col bg-[#05070d] text-slate-200 lg:min-h-screen">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3 sm:px-6">
          <div>
            <h1 className="text-lg font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>Intelligence</h1>
            <p className="text-[12px] text-slate-500">Sources, channels, and the record behind Pulse.</p>
          </div>
          <HonestyBadge kind="illustrative" />
        </div>
        <nav aria-label="Intelligence views" className="flex shrink-0 gap-1 overflow-x-auto border-b border-white/[0.06] px-3 sm:px-6">
          {TABS.map((item) => {
            const active = item.id === tab;
            return (
              <button
                key={item.id}
                type="button"
                aria-current={active ? "page" : undefined}
                onClick={() => onTabChange(item.id)}
                className={cn(
                  "shrink-0 border-b-2 px-3 py-2.5 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                  active ? "border-cyan-400 text-white" : "border-transparent text-slate-400 hover:text-white",
                )}
              >
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </div>
    </AppShell>
  );
}
