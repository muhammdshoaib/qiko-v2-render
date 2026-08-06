"use client";

/**
 * A semantic, sortable, responsive data table.
 *
 * Why hand-rolled rather than TanStack Table. With server-side pagination, sorting and filtering, a
 * table library stops being an engine and becomes a column-definition type plus three state
 * containers that this app already owns: sort lives in the URL, selection is a Set, visibility is a
 * localStorage record. Meanwhile the actual work here (scope, aria-sort, the sortable header button
 * filling its cell, the sr-only caption, the mobile card fallback, keep-previous-data dimming) is
 * work the library contributes nothing to. And the timing is bad: v8 has been frozen for sixteen
 * months and breaks under the React Compiler, while v9 shipped one day before this was written.
 *
 * The `Column` shape is deliberately close to TanStack's `ColumnDef`, so if this table ever needs
 * grouping, virtualisation or client-side faceting, the swap is mechanical and touches one file.
 *
 * Responsive strategy: a real <table> from md up, cards below. Nobody ships a seven-column table into
 * a 375px viewport and calls it responsive, and the card renderers already existed in this console.
 */
import * as React from "react";

import { cn } from "./cn";

export type SortOrder = "asc" | "desc";

export type Column<T> = {
  /** Stable id. Also the value sent as the sort key, when sortable. */
  id: string;
  header: string;
  cell: (row: T) => React.ReactNode;
  /** Sortable columns render a button in the header and own aria-sort. */
  sortable?: boolean;
  /** Right-aligned and tabular, for money and counts. */
  numeric?: boolean;
  /** Exactly one column should set this: it becomes <th scope="row"> and the sticky column. */
  rowHeader?: boolean;
  /** Hidden below the given breakpoint, so the desktop table can be denser than the card. */
  hideBelow?: "sm" | "md" | "lg";
};

export type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Screen-reader name for the table. Required: an unnamed table is an unlabelled stream of values. */
  caption: string;
  sort?: string | null;
  order?: SortOrder;
  onSortChange?: (sort: string, order: SortOrder) => void;
  /** Rendered instead of the table when there are no rows. */
  empty?: React.ReactNode;
  /** Dim rather than blank while the next page loads. */
  stale?: boolean;
  /** Optional per-row action cell, rendered in a trailing column with no header text. */
  actions?: (row: T) => React.ReactNode;
  /** Card renderer for narrow viewports. Falls back to the columns when not supplied. */
  renderCard?: (row: T) => React.ReactNode;
  className?: string;
};

const HIDE_BELOW = { sm: "hidden sm:table-cell", md: "hidden md:table-cell", lg: "hidden lg:table-cell" };

function SortButton({ column, active, order, onSortChange }: {
  column: Column<unknown>;
  active: boolean;
  order: SortOrder;
  onSortChange: (sort: string, order: SortOrder) => void;
}) {
  // Toggling an inactive column starts ascending, which is what every table people already use does.
  const next: SortOrder = active && order === "asc" ? "desc" : "asc";
  return (
    <button
      type="button"
      // Fills the header cell so the whole <th> is the target, which the ARIA practices guide calls
      // out specifically for motor-impairment users.
      className={cn("-mx-2 flex w-[calc(100%+1rem)] items-center gap-1 rounded px-2 py-1 text-left",
        "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset",
        "focus-visible:ring-ring")}
      onClick={() => onSortChange(column.id, next)}
    >
      {column.header}
      {/* A character rather than colour alone, so Windows High Contrast does not erase the cue. */}
      <span aria-hidden="true" className={cn("text-xs", active ? "opacity-100" : "opacity-30")}>
        {active && order === "desc" ? "\u25BC" : "\u25B2"}
      </span>
    </button>
  );
}

export function DataTable<T>({
  columns, rows, rowKey, caption, sort, order = "asc", onSortChange,
  empty, stale, actions, renderCard, className,
}: DataTableProps<T>) {
  if (rows.length === 0 && empty) return <>{empty}</>;

  const card = renderCard ?? ((row: T) => (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
      {columns.map((column) => (
        <React.Fragment key={column.id}>
          <dt className="text-muted-foreground">{column.header}</dt>
          <dd className={cn("min-w-0", column.numeric && "tabular-nums")}>{column.cell(row)}</dd>
        </React.Fragment>
      ))}
    </dl>
  ));

  return (
    <div className={cn(stale && "opacity-60 transition-opacity", className)}>
      {/* Cards below md. The table is genuinely unusable at 375px and W3C's own reflow guidance says
          to reduce scrolling for tabular content where you can, even though tables are exempt. */}
      <ul className="space-y-3 md:hidden">
        {rows.map((row) => (
          <li key={rowKey(row)} className="rounded-xl border border-border bg-card p-4">
            {card(row)}
            {actions && <div className="mt-3 flex flex-wrap gap-2">{actions(row)}</div>}
          </li>
        ))}
      </ul>

      {/* Negative margins let the scroll region reach the screen edges, which feels native.
          No sticky header on purpose: overflow-x makes this wrapper the vertical scroller too, so a
          sticky thead would need a bounded height, and at twenty rows a page the header barely
          leaves the viewport. A sticky header would also risk WCAG 2.4.11, where a focused row lands
          behind it. */}
      <div className="-mx-4 hidden overflow-x-auto px-4 md:block">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">
            {caption}
            {onSortChange && ". Columns with a sort control can be reordered."}
          </caption>
          <thead>
            <tr className="border-b border-border">
              {columns.map((column) => {
                const active = Boolean(sort) && sort === column.id;
                return (
                  <th
                    key={column.id}
                    scope="col"
                    // Exactly one header carries a non-none value at a time, per the ARIA practices.
                    aria-sort={column.sortable
                      ? (active ? (order === "asc" ? "ascending" : "descending") : "none")
                      : undefined}
                    className={cn(
                      "py-2 pr-3 align-bottom text-xs font-medium uppercase tracking-wide text-muted-foreground",
                      column.numeric && "text-right",
                      column.hideBelow && HIDE_BELOW[column.hideBelow],
                    )}
                  >
                    {column.sortable && onSortChange
                      ? <SortButton column={column as Column<unknown>} active={active} order={order}
                          onSortChange={onSortChange} />
                      : column.header}
                  </th>
                );
              })}
              {actions && <th scope="col" className="py-2"><span className="sr-only">Actions</span></th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-border/60 last:border-0 hover:bg-muted/40">
                {columns.map((column) => {
                  const content = (
                    <div className={cn("min-w-0", column.numeric && "tabular-nums")}>{column.cell(row)}</div>
                  );
                  // The identifying cell is a row header, which is what lets a screen reader say
                  // "Acme, plan pro" instead of reading an orphaned value.
                  return column.rowHeader ? (
                    <th key={column.id} scope="row"
                      className={cn("py-3 pr-3 font-medium",
                        column.hideBelow && HIDE_BELOW[column.hideBelow])}>
                      {content}
                    </th>
                  ) : (
                    <td key={column.id}
                      className={cn("py-3 pr-3 align-middle", column.numeric && "text-right",
                        column.hideBelow && HIDE_BELOW[column.hideBelow])}>
                      {content}
                    </td>
                  );
                })}
                {actions && (
                  <td className="py-3 text-right">
                    <div className="flex justify-end gap-2">{actions(row)}</div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
