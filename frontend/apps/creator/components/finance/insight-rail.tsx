"use client";

// Right-hand "TRENDS" rail: titled mini-cards grouped into sections (Property Performance,
// Arrears & Collections, ...). Mirrors the reference (el-finance-dashboard.png right column).
import { AlertTriangle, Building2, Tag } from "lucide-react";
import { cn } from "@qiko/ui";
import type { TrendSection } from "./utils";

const ICONS = { building: Building2, alert: AlertTriangle, tag: Tag } as const;

export function InsightRail({ sections, className, onInsightClick }: {
  sections: TrendSection[]; className?: string;
  onInsightClick?: (text: string, sectionTitle: string, insightTitle?: string) => void;
}) {
  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="flex h-14 shrink-0 items-center border-b border-border px-3">
        <div className="min-w-0 flex-1 rounded-lg border border-border bg-muted px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-indigo-200/90">Trends</p>
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {sections.length === 0 && (
          <p className="px-1 text-xs text-slate-400">Insights will appear here once analytics are available.</p>
        )}
        {sections.map((section) => {
          const Icon = ICONS[section.iconKey];
          return (
            <section key={section.title} className={cn("rounded-xl border bg-muted/50 p-3", section.border)}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <Icon className="h-4 w-4 text-white/75" />
                  <h4 className="break-words text-sm font-semibold text-foreground/88">{section.title}</h4>
                </div>
                <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px]", section.badge)}>
                  {section.insights.length} insights
                </span>
              </div>
              <div className="space-y-2">
                {section.insights.map((insight, i) => (
                  onInsightClick ? (
                    <button
                      key={`${section.title}-${i}`}
                      type="button"
                      onClick={() => onInsightClick(insight.text, section.title, insight.title)}
                      className="relative block w-full rounded-lg border border-border bg-muted px-3 py-2.5 pl-4 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300/55"
                    >
                      <span className={cn("absolute left-0 top-0 h-full w-1 rounded-l-lg", section.accent)} />
                      {insight.title ? (
                        <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-slate-600">{insight.title}</p>
                      ) : null}
                      <p className="text-[13px] leading-relaxed text-white/82">{insight.text}</p>
                    </button>
                  ) : (
                    <div key={`${section.title}-${i}`} className="relative block w-full rounded-lg border border-border bg-muted px-3 py-2.5 pl-4 text-left">
                      <span className={cn("absolute left-0 top-0 h-full w-1 rounded-l-lg", section.accent)} />
                      {insight.title ? (
                        <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-slate-600">{insight.title}</p>
                      ) : null}
                      <p className="text-[13px] leading-relaxed text-white/82">{insight.text}</p>
                    </div>
                  )
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
