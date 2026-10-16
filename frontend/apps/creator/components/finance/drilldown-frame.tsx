"use client";

import { ChevronLeft } from "lucide-react";

export function DrilldownFrame({
  backLabel = "Back to dashboard",
  onBack,
  title,
  subtitle,
  headerExtra,
  footer,
  children,
}: {
  backLabel?: string;
  onBack: () => void;
  title: string;
  subtitle?: React.ReactNode;
  headerExtra?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      className="m-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border text-foreground"
      style={{ background: "oklch(0.15 0.025 250)" }}
    >
      <div className="shrink-0 border-b border-slate-200 px-6 py-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/45"
          >
            <ChevronLeft className="h-3.5 w-3.5 shrink-0" aria-hidden />
            {backLabel}
          </button>
          {headerExtra}
        </div>
        <div className="space-y-1.5 text-left">
          <h3 className="text-lg font-semibold text-foreground/95">{title}</h3>
          {subtitle ? <div>{subtitle}</div> : null}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 pt-4">{children}</div>
      {footer}
    </section>
  );
}
