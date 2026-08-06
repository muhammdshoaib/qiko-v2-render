"use client";

/**
 * Form and overlay primitives.
 *
 * Deliberately dependency-free. This package ships raw TSX and is transpiled into BOTH apps, so
 * anything added here lands in the creator bundle too. Radix would give better menus and popovers, and
 * the creator app already carries seven `@radix-ui/*` packages, but nothing here needs a focus trap
 * that the platform does not already provide: `<dialog showModal()>` traps focus and makes the
 * background inert natively, at zero bytes, and the existing customer detail dialog already proves the
 * pattern works with correct focus restoration.
 *
 * Every control keeps the h-11 touch target the design system settled on, and every one is a real
 * native element so it stays in the natural tab order.
 */
import * as React from "react";

import { cn } from "./cn";

/* ---------- Select ---------- */

/**
 * A styled native <select>. Not a listbox re-implementation: the native control gets platform-correct
 * keyboard behaviour, type-ahead, and a usable picker on mobile for free, and those are the three
 * things hand-rolled dropdowns habitually get wrong.
 */
export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "flex h-11 w-full appearance-none rounded-md border border-input bg-background px-3 py-2 text-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        // Room for the chevron the wrapper draws, and a caret drawn in CSS so it follows the theme.
        "bg-[length:1rem] bg-[right_0.75rem_center] bg-no-repeat pr-9",
        className,
      )}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
      }}
      {...props}
    >
      {children}
    </select>
  );
}

/* ---------- Checkbox ---------- */

export function Checkbox({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="checkbox"
      className={cn(
        "size-5 shrink-0 rounded border-input text-primary accent-[var(--primary)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

/* ---------- Textarea ---------- */

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "flex min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
        "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-ring disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

/* ---------- Alert ---------- */

const ALERT_TONES = {
  info: "border-border bg-muted/40 text-foreground",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  error: "border-destructive/30 bg-destructive/10 text-destructive",
  success: "border-success/30 bg-success/10 text-success",
} as const;

/**
 * Replaces six hand-rolled amber and destructive boxes. `role` follows the tone rather than being a
 * prop: an error must interrupt a screen reader, and a notice must not, and leaving that to each call
 * site is how half of them ended up as plain paragraphs.
 */
export function Alert({ tone = "info", className, children, ...props }: {
  tone?: keyof typeof ALERT_TONES;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("rounded-xl border p-3 text-sm", ALERT_TONES[tone], className)}
      {...props}
    >
      {children}
    </div>
  );
}

/* ---------- SegmentedFilter ---------- */

export type Segment<T extends string> = { value: T; label: string };

/**
 * Promoted from the workers page, which had the only filter in the console and had it right:
 * `role="group"` with a label, and `aria-pressed` per option so the state is announced.
 */
export function SegmentedFilter<T extends string>({ label, value, options, onChange, className }: {
  label: string;
  value: T;
  options: readonly Segment<T>[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("flex flex-wrap gap-2", className)}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "inline-flex min-h-11 items-center rounded-md border px-3 text-sm transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            value === option.value
              ? "border-transparent bg-primary text-primary-foreground"
              : "border-input bg-background hover:bg-muted",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- Dialog ---------- */

/**
 * A native <dialog> with the focus handling the customer detail view already got right, extracted so
 * the next dialog does not have to rediscover it:
 *  - the opener is captured by the caller and focused again on close, after a frame, because the
 *    element must be back in the layout before it can take focus;
 *  - Escape is blocked while a mutation is in flight, so a half-submitted change cannot be abandoned;
 *  - `showModal()` provides the focus trap and background inertness, so no library is needed.
 */
export function Dialog({ open, onClose, opener, busy = false, labelledBy, className, children }: {
  open: boolean;
  onClose: () => void;
  opener?: HTMLElement | null;
  busy?: boolean;
  labelledBy: string;
  className?: string;
  children: React.ReactNode;
}) {
  const ref = React.useRef<HTMLDialogElement>(null);

  React.useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={labelledBy}
      onClose={() => {
        onClose();
        requestAnimationFrame(() => opener?.focus());
      }}
      onCancel={(event) => { if (busy) event.preventDefault(); }}
      className={cn(
        "w-[min(94vw,42rem)] rounded-2xl border border-border bg-card p-5 text-foreground",
        "backdrop:bg-black/50",
        className,
      )}
    >
      {open && children}
    </dialog>
  );
}

/* ---------- Pagination ---------- */

/**
 * Hand-rolled in three places with three slightly different behaviours. The result count belongs here
 * rather than in the page, because "Showing 21-40 of 137" is the string that makes the live region
 * announce anything: a bare total is identical before and after a filter that returns the same count
 * of a different set.
 */
export function Pagination({ page, pageCount, total, shown, label, busy, onChange }: {
  page: number;
  pageCount: number;
  total: number;
  shown: number;
  /** Plural noun for the rows, e.g. "workers". */
  label: string;
  busy?: boolean;
  onChange: (page: number) => void;
}) {
  const first = shown === 0 ? 0 : (page - 1) * Math.max(1, Math.ceil(total / Math.max(pageCount, 1))) + 1;
  return (
    <nav aria-label={`${label} pagination`} className="flex items-center justify-between gap-3 pt-2">
      <button
        type="button"
        className={cn("inline-flex min-h-11 items-center rounded-md border border-input px-3 text-sm",
          "hover:bg-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
        disabled={page <= 1 || busy}
        onClick={() => onChange(Math.max(1, page - 1))}
      >
        Previous
      </button>
      <span className="text-sm text-muted-foreground">
        Page {page} of {pageCount}
      </span>
      <button
        type="button"
        className={cn("inline-flex min-h-11 items-center rounded-md border border-input px-3 text-sm",
          "hover:bg-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
        disabled={page >= pageCount || busy}
        onClick={() => onChange(page + 1)}
      >
        Next
      </button>
      <span className="sr-only">{first} to {first + Math.max(0, shown - 1)} of {total} {label}</span>
    </nav>
  );
}
