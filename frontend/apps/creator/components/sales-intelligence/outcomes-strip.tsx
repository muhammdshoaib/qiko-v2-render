"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "@qiko/ui";

export type OutcomeTile = { value: string; label: string; caption?: string; trend?: "up" | "down" | "neutral" };

// Tailwind's JIT scanner needs static class names, not string-interpolated ones -- map the tile
// count to a fixed class instead of building `grid-cols-${n}` at runtime.
const GRID_COLS: Record<number, string> = {
  3: "grid-cols-2 sm:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-4",
  5: "grid-cols-2 sm:grid-cols-5",
};

export function OutcomesStrip({ title, tiles }: { title: string; tiles: OutcomeTile[] }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-6">
      <p className="mb-5 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">OUTCOMES &ndash; {title}</p>
      <div className={cn("grid gap-6", GRID_COLS[tiles.length] ?? "grid-cols-2 sm:grid-cols-4")}>
        {tiles.map((t) => (
          <div key={t.label}>
            <p className="text-3xl font-bold tracking-tight text-white">{t.value}</p>
            <p className="mt-1 text-[13px] text-slate-400">{t.label}</p>
            {t.caption && (
              <p className={cn("mt-2 flex items-center gap-1 text-[11px] font-medium",
                t.trend === "down" ? "text-red-400" : t.trend === "up" ? "text-emerald-400" : "text-slate-500")}>
                {t.trend === "up" && <ArrowUp className="size-3" />}
                {t.trend === "down" && <ArrowDown className="size-3" />}
                {t.caption}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
