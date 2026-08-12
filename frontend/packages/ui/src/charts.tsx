"use client";

/**
 * Two chart primitives, drawn as SVG rather than pulled from a library.
 *
 * WHY NO CHART LIBRARY. Recharts and its peers are 400kb-plus of runtime for what this console needs,
 * which is one trend line and one ranked bar list. The admin app is an internal tool loaded over the
 * public internet by people who are usually in a hurry, and a dependency that large has to earn its
 * place by doing something hard. Axes, legends, brushes and animated tooltips are not what is being
 * asked for here.
 *
 * WHAT IS NOT NEGOTIABLE IS ACCESSIBILITY, which is the usual casualty of a hand-rolled chart. An SVG
 * with no text in it is invisible to a screen reader and unreadable to anyone who cannot distinguish
 * the colours. So every chart here carries a summary as its accessible name AND renders the underlying
 * figures as a visually hidden table. The table is the real content; the drawing is a convenience for
 * people who can see it.
 *
 * They are also deliberately not interactive. A tooltip that appears on hover is unreachable by
 * keyboard and absent on touch, so the numbers that matter are in the table and in the labels rather
 * than hidden behind a pointer.
 */
import * as React from "react";

import { cn } from "./cn";

export type SeriesPoint = { label: string; value: number };

function VisuallyHiddenTable({ caption, rows, format }: {
  caption: string;
  rows: SeriesPoint[];
  format: (value: number) => string;
}) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr><th scope="col">Period</th><th scope="col">Value</th></tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}><th scope="row">{row.label}</th><td>{format(row.value)}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * A filled trend line over evenly spaced points.
 *
 * Scaled from zero rather than from the minimum. A chart that starts its axis at the lowest value makes
 * a 2% variation look like a cliff, which is the single most common way a dashboard misleads the person
 * reading it. If the variation is genuinely small, it should look small.
 */
export function TrendChart({
  points, label, format = (v) => String(v), className, height = 120,
}: {
  points: SeriesPoint[];
  /** Used as the accessible name and the hidden table's caption. */
  label: string;
  format?: (value: number) => string;
  className?: string;
  height?: number;
}) {
  if (points.length === 0) {
    return <p className={cn("text-sm text-muted-foreground", className)}>No data for this period.</p>;
  }

  const width = 600;
  const peak = Math.max(...points.map((p) => p.value), 0);
  // A flat zero series still has to draw a baseline rather than divide by zero.
  const scale = peak > 0 ? peak : 1;
  const step = points.length > 1 ? width / (points.length - 1) : 0;
  const y = (value: number) => height - (value / scale) * (height - 8) - 4;
  const line = points.map((p, i) => `${i * step},${y(p.value)}`).join(" ");
  const area = `0,${height} ${line} ${(points.length - 1) * step},${height}`;

  const total = points.reduce((sum, p) => sum + p.value, 0);
  const summary = `${label}. ${points.length} points, total ${format(total)}, peak ${format(peak)}.`;

  return (
    <div className={className}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img"
        aria-label={summary} className="h-[120px] w-full overflow-visible">
        <polygon points={area} className="fill-primary/10" />
        <polyline points={line} fill="none" strokeWidth="2" vectorEffect="non-scaling-stroke"
          className="stroke-primary" strokeLinejoin="round" strokeLinecap="round" />
        {/* The last point marked, because "where are we now" is the question a trend is read for. */}
        <circle cx={(points.length - 1) * step} cy={y(points[points.length - 1].value)} r="3"
          className="fill-primary" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-1 flex justify-between text-xs text-muted-foreground">
        <span>{points[0].label}</span>
        <span>{points[points.length - 1].label}</span>
      </div>
      <VisuallyHiddenTable caption={label} rows={points} format={format} />
    </div>
  );
}

/**
 * A ranked list of bars, for categorical breakdowns like plan mix or spend by model.
 *
 * The value is printed next to every bar. A bar whose length is the only encoding of its value forces
 * the reader to estimate against a scale that is not drawn, and they will estimate wrong.
 */
export function BarList({
  items, label, format = (v) => String(v), className, max: explicitMax, emptyMessage = "Nothing to show.",
}: {
  items: SeriesPoint[];
  label: string;
  format?: (value: number) => string;
  className?: string;
  /** Scale against a known total instead of the largest item, when the parts should read as a share. */
  max?: number;
  emptyMessage?: string;
}) {
  if (items.length === 0) {
    return <p className={cn("text-sm text-muted-foreground", className)}>{emptyMessage}</p>;
  }
  const ceiling = explicitMax ?? Math.max(...items.map((i) => i.value), 1);

  return (
    <div className={cn("space-y-2", className)}>
      <ul aria-label={label} className="space-y-2">
        {items.map((item) => (
          <li key={item.label} className="space-y-1">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate">{item.label}</span>
              <span className="shrink-0 font-medium tabular-nums">{format(item.value)}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary"
                style={{ width: `${Math.max(2, (item.value / ceiling) * 100)}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
