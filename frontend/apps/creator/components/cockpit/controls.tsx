"use client";

// Canonical dark-theme form controls shared across the IDG worker cockpits (Sales Intelligence,
// Pre-Sales). Every text input / textarea / native <select> / on-off switch in the cockpits should
// use these primitives so they all share one identical look and focus / disabled behaviour on the
// #05070d cockpit surface (bg-muted · border-border · rounded-lg · indigo focus ring),
// instead of the previous ad-hoc / native-unstyled controls. Styling only -- these forward every
// native prop (value, onChange, disabled, aria-*, id, placeholder, …) unchanged.
import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@qiko/ui";

// One shared base so height/padding/radius/border/bg + focus + disabled states can never drift
// between the different control types.
const CONTROL_BASE =
  "w-full rounded-lg border border-border bg-muted text-sm text-slate-700 " +
  "placeholder:text-slate-500 transition-colors " +
  "focus-visible:border-indigo-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 " +
  "disabled:cursor-not-allowed disabled:opacity-50";

/* ---------- Text input ---------- */
export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(CONTROL_BASE, "px-3 py-2", className)} {...props} />;
}

/* ---------- Textarea ---------- */
export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(CONTROL_BASE, "resize-y px-3 py-2 leading-relaxed", className)} {...props} />;
}

/* ---------- Native <select> with a chevron ---------- */
// `className` styles the <select> itself; `wrapperClassName` sizes/positions the relative wrapper
// (e.g. `max-w-[160px]`, `min-w-0 flex-1`) so layout callers keep full control.
export function Select({
  className, wrapperClassName, children, ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { wrapperClassName?: string }) {
  return (
    <div className={cn("relative", wrapperClassName)}>
      <select
        className={cn(
          CONTROL_BASE,
          "appearance-none px-3 py-2 pr-9 [&>option]:bg-white [&>option]:text-slate-700",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
    </div>
  );
}

/* ---------- Switch (accessible on/off toggle) ---------- */
// Rendered as a real <button role="switch">, so keyboard toggle (Space/Enter) + focus ring come for
// free. `label` becomes the accessible name; pass `checked` + `onCheckedChange`.
export function Switch({
  checked, onCheckedChange, label, className, disabled, ...props
}: Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onClick" | "aria-label" | "aria-checked" | "type"> & {
  checked: boolean;
  onCheckedChange?: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onCheckedChange}
      className={cn(
        // inline-flex + items-center centres the thumb without absolute/top hacks; p-0 + a
        // transparent border neutralise the browser's default <button> chrome so it always
        // reads as a switch. The off-state track stays visible on the dark cockpit surface.
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border p-0 transition-colors " +
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[#05070d] " +
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-indigo-500 bg-indigo-500" : "border-border bg-white/20",
        className,
      )}
      {...props}
    >
      <span className={cn(
        "pointer-events-none inline-block size-4 transform rounded-full bg-white shadow-sm ring-1 ring-black/10 transition-transform duration-200",
        checked ? "translate-x-[18px]" : "translate-x-0.5",
      )} />
    </button>
  );
}
