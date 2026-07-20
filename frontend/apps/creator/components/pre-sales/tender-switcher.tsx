"use client";

// Custom dark-themed tender switcher for the Pre-Sales cockpit top bar. Replaces the shared native
// <select>, whose OS-rendered option list opens in a light-grey style on iPad / Safari that clashes
// with the dark cockpit. This renders its own popover so the list matches the app on every browser.
// Behaviour-preserving: selecting an option simply calls the existing onSelectPack(id).
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@qiko/ui";
import type { RfpPack } from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";

export function TenderSwitcher({
  packs, activePackId, onSelectPack, className,
}: {
  packs: RfpPack[];
  activePackId: string | null;
  onSelectPack: (packId: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const active = packs.find((p) => p.id === activePackId) ?? null;

  // Close on outside-click and on Escape, so the popover never lingers over the cockpit.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Switch active tender"
        className={cn(
          "flex w-full items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 transition-colors",
          "hover:bg-white/[0.06] focus-visible:border-indigo-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
        )}
      >
        <span className="min-w-0 flex-1 truncate text-left">{active?.title ?? "Select tender"}</span>
        <ChevronDown aria-hidden="true" className={cn("size-4 shrink-0 text-slate-500 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label="Tenders"
          className="absolute right-0 z-50 mt-1 max-h-[60vh] w-[260px] overflow-y-auto rounded-lg border border-white/10 bg-[#05070d] p-1 shadow-xl shadow-black/50"
        >
          {packs.map((p) => {
            const isActive = p.id === activePackId;
            return (
              <li key={p.id} role="option" aria-selected={isActive}>
                <button
                  type="button"
                  onClick={() => { onSelectPack(p.id); setOpen(false); }}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                    isActive ? "bg-indigo-500/10 text-white" : "text-slate-300 hover:bg-white/[0.06] hover:text-white",
                  )}
                >
                  <Check aria-hidden="true" className={cn("mt-0.5 size-4 shrink-0", isActive ? "text-indigo-400" : "text-transparent")} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium">{p.title}</span>
                    {p.deadline && (
                      <span className="block text-[11px] text-slate-500">Due {formatShortDate(p.deadline)}</span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
