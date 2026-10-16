"use client";

import { useId } from "react";
import { Info } from "lucide-react";

export function MetricInfoTooltip({ label, description }: { label: string; description: string }) {
  const tooltipId = useId();

  return (
    <span className="group/metric-info relative inline-flex shrink-0 align-middle">
      <button
        type="button"
        aria-label={`More information about ${label}`}
        aria-describedby={tooltipId}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onPointerDown={(event) => event.stopPropagation()}
        className="inline-flex size-5 items-center justify-center rounded-full text-slate-500 transition-colors hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-1 focus-visible:ring-offset-[#05070d]"
      >
        <Info aria-hidden="true" className="size-3.5" />
      </button>
      <span
        id={tooltipId}
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-1/2 z-30 mb-2 w-64 -translate-x-1/2 rounded-lg border border-border bg-white px-3 py-2 text-left text-[11px] font-normal normal-case leading-4 tracking-normal text-slate-100 opacity-0 shadow-xl transition-opacity group-hover/metric-info:visible group-hover/metric-info:opacity-100 group-focus-within/metric-info:visible group-focus-within/metric-info:opacity-100"
      >
        {description}
      </span>
    </span>
  );
}
