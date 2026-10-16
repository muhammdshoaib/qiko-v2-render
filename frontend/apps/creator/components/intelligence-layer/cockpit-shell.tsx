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
      <div className="flex min-h-[calc(100dvh-3.5rem)] flex-col bg-slate-50 text-slate-800 lg:min-h-screen">
        {tab !== "intelligence" && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
              <div>
                <h1 className="text-lg font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>Setup</h1>
                <p className="text-[12px] text-slate-400">Connections, sources, and channel surfaces.</p>
              </div>
              <HonestyBadge kind="illustrative" />
            </div>
            <nav aria-label="Intelligence views" className="flex shrink-0 gap-1 overflow-x-auto border-b border-border px-3 sm:px-6">
              {TABS.filter((item) => item.id !== "intelligence").map((item) => {
                const active = item.id === tab;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-current={active ? "page" : undefined}
                    onClick={() => onTabChange(item.id)}
                    className={cn(
                      "shrink-0 border-b-2 px-3 py-2.5 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
                      active ? "border-indigo-500 text-foreground" : "border-transparent text-slate-500 hover:text-foreground",
                    )}
                  >
                    {item.label}
                  </button>
                );
              })}
            </nav>
          </>
        )}
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </div>
    </AppShell>
  );
}
