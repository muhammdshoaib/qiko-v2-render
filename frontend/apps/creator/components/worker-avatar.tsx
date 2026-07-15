// One shared worker avatar treatment used across the Creator dashboard, workers list and worker
// detail so the icon/colour never drifts between views. It mirrors the cockpit iconography: an
// indigo->violet gradient square with a per-type lucide icon (Bot / FileText / Radar / LineChart),
// plus an optional emerald "ready" status dot. Styling only -- no data fetching or behaviour.
import { Bot, FileText, LineChart, Radar, type LucideIcon } from "lucide-react";
import { cn } from "@qiko/ui";

// Per-vertical icon, keyed off Agent.atype. Unknown/legacy types get the generic Bot.
export function workerTypeIcon(atype?: string | null): LucideIcon {
  switch ((atype ?? "").trim()) {
    case "pre_sales_writer":
      return FileText;
    case "sales_intelligence":
      return Radar;
    case "finance":
      return LineChart;
    default:
      return Bot;
  }
}

const SIZE_STYLES = {
  sm: { box: "size-10 rounded-xl", icon: "size-5", dot: "size-3.5 border-2" },
  md: { box: "size-12 rounded-xl", icon: "size-6", dot: "size-4 border-2" },
  lg: { box: "size-14 rounded-2xl", icon: "size-7", dot: "size-4 border-2" },
} as const;

export function WorkerAvatar({
  atype,
  size = "md",
  ready = false,
  className,
}: {
  atype?: string | null;
  size?: keyof typeof SIZE_STYLES;
  ready?: boolean;
  className?: string;
}) {
  const Icon = workerTypeIcon(atype);
  const s = SIZE_STYLES[size];
  return (
    <div className={cn("relative shrink-0", className)}>
      <div className={cn("grid place-items-center bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-500/20", s.box)}>
        <Icon className={s.icon} aria-hidden="true" />
      </div>
      {ready && (
        <span className={cn("absolute -bottom-0.5 -right-0.5 rounded-full border-[#05070d] bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]", s.dot)} />
      )}
    </div>
  );
}
