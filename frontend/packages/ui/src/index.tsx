import * as React from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { cva, type VariantProps } from "class-variance-authority";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/* ---------- Button ---------- */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium " +
    "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
    "focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none " +
    "disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        outline: "border border-border bg-transparent hover:bg-muted",
        ghost: "hover:bg-muted",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      // 44px is the WCAG 2.5.5 / Apple HIG minimum touch target, and these primitives were below it:
      // Input and the default Button were 40px, the icon Button 40x40. Fixed here rather than per page,
      // because a per-usage className has to be repeated at all 19 call sites and will be forgotten at
      // the 20th. The chat composers, including the PUBLIC embed widget, put an Input next to an icon
      // Button in the same flex row, so the two must move together or they misalign by 4px.
      //
      // sm stays at 32px on purpose: it is a compact secondary action (30 uses, all next to a larger
      // primary control), and raising it would remove the only compact variant. WCAG allows this where
      // an equivalent control is available; do not use sm as the primary action on a mobile surface.
      size: { sm: "h-8 px-3", default: "h-11 px-4 py-2", lg: "h-12 px-6", icon: "size-11" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

/* ---------- Input / Label ---------- */
export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        // h-11, not h-10: see the touch target note on the Button size variants above.
        "flex h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
        "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-ring disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-sm font-medium text-foreground", className)} {...props} />;
}

/* ---------- Card ---------- */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-border bg-card text-card-foreground shadow-sm", className)} {...props} />;
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-6", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-lg font-semibold leading-none tracking-tight", className)} {...props} />;
}
export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />;
}
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-0", className)} {...props} />;
}

/* ---------- Badge ---------- */
const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-transparent bg-primary/10 text-primary",
      muted: "border-transparent bg-muted text-muted-foreground",
      // Matches the live site's worker-status pills exactly: emerald/amber/red with a matching
      // translucent border, not just a flat fill.
      success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
      warning: "border-amber-500/30 bg-amber-500/10 text-amber-400",
      destructive: "border-destructive/30 bg-destructive/10 text-destructive",
    },
  },
  defaultVariants: { variant: "default" },
});
export function Badge({ className, variant, dot, ...props }:
  React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants> & { dot?: boolean }) {
  const dotColor = variant === "success" ? "bg-emerald-400" : variant === "warning" ? "bg-amber-400" : variant === "destructive" ? "bg-destructive" : "bg-current";
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot && <span className={cn("size-1.5 shrink-0 rounded-full animate-pulse", dotColor)} />}
      {props.children}
    </span>
  );
}

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

/* ---------- Brand ---------- */
export function Logo({ className, iconOnly = false }: { className?: string; iconOnly?: boolean }) {
  // Official Qiko wordmark / icon (assets live in each app's /public).
  const src = iconOnly ? "/qiko-icon.png" : "/qiko-logo.webp";
  return <img src={src} alt="Qiko" className={cn(iconOnly ? "h-8 w-8" : "h-7 w-auto", className)} />;
}
