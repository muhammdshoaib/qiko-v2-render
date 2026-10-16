// One shared worker avatar treatment used across the Creator dashboard, workers list and worker
// detail so the avatar never drifts between views. It matches the idg-sales.qiko.ai reference: a
// cyan->blue gradient rounded square showing the worker's LETTER-INITIAL (first character of the
// name) in bold white, plus an optional emerald "ready" status dot. Styling only -- no data
// fetching or behaviour. The per-type lucide icon (workerTypeIcon) is still exported for the
// workers-list GROUP headers.
import { Activity, Bot, FileText, LineChart, Radar, type LucideIcon } from "lucide-react";
import { cn } from "@qiko/ui";

// Per-vertical icon, keyed off Agent.atype. Unknown/legacy types get the generic Bot. Used for the
// workers-list group headers (NOT the per-worker avatar, which is a letter-initial).
export function workerTypeIcon(atype?: string | null): LucideIcon {
  switch ((atype ?? "").trim()) {
    case "pre_sales_writer":
      return FileText;
    case "sales_intelligence":
      return Radar;
    case "finance":
      return LineChart;
    case "intelligence":
      return Activity;
    default:
      return Bot;
  }
}

const SIZE_STYLES = {
  sm: { box: "size-10 rounded-xl text-base", dot: "size-3.5 border-2" },
  md: { box: "size-12 rounded-xl text-lg", dot: "size-4 border-2" },
  lg: { box: "size-14 rounded-2xl text-2xl", dot: "size-4 border-2" },
} as const;

// First character of the worker name, upper-cased. Falls back to "?" for empty/unnamed workers.
function initialOf(name?: string | null): string {
  const trimmed = (name ?? "").trim();
  return trimmed ? trimmed[0]!.toUpperCase() : "?";
}

export function WorkerAvatar({
  name,
  size = "md",
  ready = false,
  className,
}: {
  name?: string | null;
  size?: keyof typeof SIZE_STYLES;
  ready?: boolean;
  className?: string;
}) {
  const s = SIZE_STYLES[size];
  return (
    <div className={cn("relative shrink-0", className)}>
      <div className={cn("grid place-items-center bg-gradient-to-br from-indigo-500 to-violet-600 font-bold text-foreground shadow-lg shadow-indigo-200", s.box)}>
        <span aria-hidden="true">{initialOf(name)}</span>
      </div>
      {ready && (
        <span className={cn("absolute -bottom-0.5 -right-0.5 rounded-full border-[#05070d] bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]", s.dot)} />
      )}
    </div>
  );
}
