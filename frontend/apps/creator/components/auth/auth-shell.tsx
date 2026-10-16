"use client";

import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { Link } from "@/lib/wouter";
import { Card } from "@/components/ui/card";
import { cn } from "@qiko/ui";

/** Shared light auth surface — Signal-like white cards on a soft slate field. */
export const AUTH_INPUT =
  "border-slate-200 bg-white text-slate-900 placeholder:text-slate-400 focus-visible:border-indigo-400 focus-visible:ring-indigo-300/40";

export const AUTH_BUTTON =
  "min-h-11 w-full border-0 bg-indigo-600 text-white shadow-sm hover:bg-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-300 sm:min-h-10";

export const AUTH_LABEL = "text-slate-700";

export const AUTH_MUTED = "text-slate-500";

export function AuthShell({
  children,
  backHref = "/",
  backLabel = "Back to home",
  className,
  cardClassName,
}: {
  children: ReactNode;
  backHref?: string;
  backLabel?: string;
  className?: string;
  cardClassName?: string;
}) {
  return (
    <div
      className={cn("relative flex min-h-screen items-center justify-center bg-slate-50 p-4", className)}
      style={{ paddingBottom: "max(1rem, var(--consent-banner-offset, 1rem))" }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute -left-24 top-0 h-[28rem] w-[28rem] rounded-full bg-indigo-100/70 blur-3xl" />
        <div className="absolute -right-20 bottom-0 h-[24rem] w-[24rem] rounded-full bg-sky-100/60 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, rgba(148,163,184,0.35) 1px, transparent 0)",
            backgroundSize: "24px 24px",
          }}
        />
      </div>

      <div className="relative z-10 w-full max-w-md">
        <Link
          href={backHref}
          className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition-colors hover:text-slate-900"
        >
          <ArrowLeft className="size-4" />
          {backLabel}
        </Link>

        <Card
          className={cn(
            "overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_8px_30px_-12px_rgba(15,23,42,0.12)]",
            cardClassName,
          )}
        >
          {children}
        </Card>
      </div>
    </div>
  );
}

export function AuthLogo() {
  return (
    <img
      src="/qiko-logo-email.png"
      alt="Qiko"
      width={120}
      height={48}
      className="mx-auto mb-4 h-12 w-[120px] object-contain"
    />
  );
}

export function AuthError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3">
      <p className="text-sm text-red-700">{message}</p>
    </div>
  );
}
