"use client";

import { useRouter } from "next/navigation";
import { useFinance } from "./finance-context";
import { DrilldownFrame } from "./drilldown-frame";
import { kpiMetricDrilldown, type KpiMetricKey } from "./utils";

export function KpiDetailPanel({ metric }: { metric: KpiMetricKey }) {
  const { agentId, analytics, currency } = useFinance();
  const router = useRouter();
  const data = kpiMetricDrilldown(analytics?.summary, metric, currency);

  return (
    <DrilldownFrame
      onBack={() => router.push(`/studio/${agentId}/finance`)}
      title={data.title}
      subtitle={<p className="text-2xl font-bold leading-tight text-foreground/95 tabular-nums">{data.formatted}</p>}
    >
      {data.details.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {data.details.map(([label, value]) => (
            <div key={label} className="rounded-lg border border-border bg-muted p-3">
              <p className="text-[10px] font-medium uppercase tracking-wider text-slate-400">{label}</p>
              <p className="mt-1 break-words text-sm font-semibold text-foreground/90">{value}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-border bg-muted/50 px-3 py-3 text-xs leading-relaxed text-white/48">
          No extra details available for this card in the current API response.
        </p>
      )}
    </DrilldownFrame>
  );
}
